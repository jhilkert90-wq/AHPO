"""Async coordinator: tracks mapped entities, drives the learning engine, writes the pump speed.

Update strategy: event-driven (state-change listeners on the tracked entities) plus a
short periodic tick, so elapsed-time bookkeeping (settling/averaging) advances even
when no entity has changed value recently.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    CONF_CHARGE_PUMP_SPEED_INPUT,
    CONF_CHARGE_PUMP_SPEED_OUTPUT,
    CONF_COMPRESSOR_FREQUENCY,
    CONF_ERROR_STATUS,
    CONF_OPERATING_MODE,
    CONF_OUTDOOR_TEMP,
    REQUIRED_ENTITY_KEYS,
)
from .core.cop import calculate_cop_for_row
from .core.phase_manager import Phase, PhaseManager
from .core.timing import Observation, SteadyPeriodDetector
from .learning import LearningEngine, LearningResult

_LOGGER = logging.getLogger(__name__)

TICK_INTERVAL = timedelta(seconds=5)


class AhpoCoordinator:
    """Ties together entity reads, the learning engine, and the Phase B pump-speed write."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_map: dict[str, str],
        learning_engine: LearningEngine,
        phase_manager: PhaseManager,
    ) -> None:
        self._hass = hass
        self._entity_map = entity_map
        self._learning_engine = learning_engine
        self.phase_manager = phase_manager
        self._detector = SteadyPeriodDetector()
        self.last_result: LearningResult | None = None
        self.last_observation: Observation | None = None
        self.pump_write_error = False
        self._unsubscribers: list[Any] = []
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Register a callback invoked after every processed learning cycle (entity push updates)."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.remove(listener)

    def async_start(self) -> None:
        """Start listening for entity changes and the periodic bookkeeping tick."""
        tracked_entities = [
            entity_id
            for key, entity_id in self._entity_map.items()
            if key in (CONF_CHARGE_PUMP_SPEED_INPUT, CONF_COMPRESSOR_FREQUENCY, CONF_OUTDOOR_TEMP)
        ]
        self._unsubscribers.append(
            async_track_state_change_event(self._hass, tracked_entities, self._async_on_state_change)
        )
        self._unsubscribers.append(
            async_track_time_interval(self._hass, self._async_on_tick, TICK_INTERVAL)
        )

    def async_stop(self) -> None:
        """Unsubscribe all listeners (called from async_unload_entry)."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    @callback
    def _async_on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._tick(datetime.now().astimezone())

    @callback
    def _async_on_tick(self, now: datetime) -> None:
        self._tick(now)

    def _tick(self, now: datetime) -> None:
        row = self._read_entities()
        if row is None:
            self._detector.reset()  # sensor unavailable -> discard the in-progress period
            return

        cop = calculate_cop_for_row(row)
        if math.isnan(cop):
            return

        observation = self._detector.observe(
            timestamp=now,
            outdoor_temp=row["outdoor_temp"],
            compressor_frequency=row["compressor_frequency"],
            charge_pump_speed=row[CONF_CHARGE_PUMP_SPEED_INPUT],
            cop=cop,
        )
        if observation is None:
            return

        result = self._learning_engine.process(observation, error_status=self._read_error_status())
        self.last_result = result
        self.last_observation = observation
        _LOGGER.debug("Learning cycle: phase=%s cell=%s", result.phase, result.cell)

        if result.phase is Phase.ACTIVE and result.proposed_charge_pump_speed is not None:
            self._hass.async_create_task(
                self._async_write_pump_speed(result.proposed_charge_pump_speed)
            )

        for listener in self._listeners:
            listener()

    def _read_entities(self) -> dict[str, float] | None:
        """Read all mapped entities as floats; returns None if anything is unavailable."""
        row: dict[str, float] = {}
        for key in REQUIRED_ENTITY_KEYS:
            entity_id = self._entity_map.get(key)
            state = self._hass.states.get(entity_id) if entity_id else None
            if state is None or state.state in ("unknown", "unavailable"):
                return None
            try:
                row[key] = float(state.state)
            except ValueError:
                return None

        operating_mode_entity = self._entity_map.get(CONF_OPERATING_MODE)
        if operating_mode_entity:
            state = self._hass.states.get(operating_mode_entity)
            if state is not None and state.state not in ("unknown", "unavailable"):
                try:
                    row["operating_mode"] = float(state.state)
                except ValueError:
                    pass
        return row

    def _read_error_status(self) -> bool:
        """Safety fallback input: mapped error-status entity 'on', or a failed pump write, forces Phase A."""
        if self.pump_write_error:
            return True
        entity_id = self._entity_map.get(CONF_ERROR_STATUS)
        if not entity_id:
            return False
        state = self._hass.states.get(entity_id)
        return state is not None and state.state == "on"

    async def _async_write_pump_speed(self, speed: float) -> None:
        """Write the proposed speed to the mapped pump output entity (Phase B only).

        If no output entity is configured (passive-only mode), the write is silently
        skipped.  Any failure (unsupported domain, service-call error) sets
        pump_write_error, which forces Phase A on the next cycle until a write succeeds.
        """
        entity_id = self._entity_map.get(CONF_CHARGE_PUMP_SPEED_OUTPUT)
        if not entity_id:
            # Passive-only mode — no writable entity configured.
            return
        domain = entity_id.split(".", 1)[0]
        if domain not in ("number", "input_number"):
            _LOGGER.error("Cannot write charge_pump_speed: unsupported entity domain %r", domain)
            self.pump_write_error = True
            return
        try:
            await self._hass.services.async_call(
                domain, "set_value", {"entity_id": entity_id, "value": speed}, blocking=True
            )
        except Exception:  # noqa: BLE001 - any failure must trigger the safety fallback, not crash
            _LOGGER.exception("Failed to write charge_pump_speed to %s", entity_id)
            self.pump_write_error = True
        else:
            self.pump_write_error = False
