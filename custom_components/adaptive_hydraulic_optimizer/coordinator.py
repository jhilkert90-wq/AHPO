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
    CONF_CHARGE_PUMP_SPEED_OUTPUT_COOL,
    CONF_CHARGE_PUMP_SPEED_OUTPUT_DHW,
    CONF_CHARGE_PUMP_SPEED_OUTPUT_HEAT,
    CONF_COMPRESSOR_FREQUENCY,
    CONF_DHW_TARGET_TEMP,
    CONF_ERROR_STATUS,
    CONF_PRIMARY_FLOW_TEMP,
    CONF_OPERATING_MODE,
    CONF_OUTDOOR_TEMP,
    REQUIRED_ENTITY_KEYS,
)
from .core.cop import calculate_cop_for_row, calculate_delta_t, calculate_secondary_delta_t, calculate_spread_error_for_row, resolve_mode
from .core.hw_strategy import DHW_MODE, DhwController, clamp_standby_speed, is_dhw_state
from .core.phase_manager import Phase, PhaseManager
from .core.timing import Observation, SteadyPeriodDetector
from .decision_log import DecisionLogger, build_decision_entry
from .learning import LearningEngine, LearningResult

_LOGGER = logging.getLogger(__name__)

TICK_INTERVAL = timedelta(seconds=1)
STANDARD_TICK_INTERVAL = timedelta(seconds=5)  # heat/cool cadence (unchanged)

_VALID_MODE_STATES = frozenset({"heat", "cool"})


def _resolve_operating_mode(raw_state: str | None, dhw_state: str | None = None) -> str | None:
    """Normalise a raw operating-mode entity state to 'heat'/'cool'/'dhw', else None."""
    if raw_state is None:
        return None
    if is_dhw_state(raw_state, dhw_state):
        return DHW_MODE
    mode = raw_state.strip().lower()
    return mode if mode in _VALID_MODE_STATES else None


class AhpoCoordinator:
    """Ties together entity reads, the learning engine, and the Phase B pump-speed write."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_map: dict[str, str],
        learning_engine: LearningEngine,
        phase_manager: PhaseManager,
        min_compressor_frequency: float = 20.0,
        min_charge_pump_speed: float = 15.0,
        min_speed_step_percent: float = 0.0,
        settling_time_minutes: float | None = None,
        averaging_time_minutes: float | None = None,
        decision_logger: DecisionLogger | None = None,
        dhw_mode_state: str = "hw",
        dhw_standby_speed: float = 30.0,
        dhw_control_interval_s: float = 5.0,
        dhw_controller: DhwController | None = None,
    ) -> None:
        self._hass = hass
        self._entity_map = entity_map
        self._learning_engine = learning_engine
        self.phase_manager = phase_manager
        self._min_compressor_frequency = min_compressor_frequency
        self._min_charge_pump_speed = min_charge_pump_speed
        self._min_speed_step_percent = min_speed_step_percent
        self._detector = SteadyPeriodDetector(
            settling_minutes=settling_time_minutes,
            averaging_minutes=averaging_time_minutes,
        )
        from .core.timing import AVERAGING_TIME_MINUTES as _AVG_DEFAULT
        self._averaging_time_minutes: float = averaging_time_minutes if averaging_time_minutes is not None else _AVG_DEFAULT
        self._decision_logger = decision_logger
        self._dhw_mode_state = dhw_mode_state
        self.dhw_standby_speed = dhw_standby_speed
        self.dhw_control_interval_s = dhw_control_interval_s
        self._dhw_controller = dhw_controller or DhwController(min_speed=min_charge_pump_speed)
        self._last_dhw_eval: datetime | None = None
        self._last_standard_tick: datetime | None = None
        self._dhw_standby_written: float | None = None
        self.dhw_active = False
        self._last_written_speed: float | None = None
        self._last_written_speeds: dict[tuple[str, str], float] = {}
        self.last_result: LearningResult | None = None
        self.last_observation: Observation | None = None
        self.last_primary_delta_t: float | None = None
        self.last_secondary_delta_t: float | None = None
        self.current_operating_mode: str | None = None
        self.pump_write_error = False
        self._unsubscribers: list[Any] = []
        self._listeners: list[Callable[[], None]] = []

    @property
    def averaging_time_minutes(self) -> float:
        """Configured averaging window duration in minutes."""
        return self._averaging_time_minutes

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
        # The timer runs at a fine resolution for HW; heat/cool keeps its 5 s cadence.
        if self._read_operating_mode() != DHW_MODE:
            if (
                self._last_standard_tick is not None
                and now - self._last_standard_tick < STANDARD_TICK_INTERVAL
            ):
                return
            self._last_standard_tick = now
        self._tick(now)

    def _tick(self, now: datetime) -> None:
        operating_mode = self._read_operating_mode()
        if operating_mode == DHW_MODE:
            self.current_operating_mode = operating_mode
            self._tick_dhw(now)
            return
        if self.dhw_active:
            # Left HW: reset HW state; the standard strategy restarts with settling/averaging.
            self.dhw_active = False
            self._dhw_controller.reset()
            self._dhw_standby_written = None
            self._last_dhw_eval = None
            self._last_written_speed = None
            self._detector.reset()

        row, operating_mode = self._read_entities()
        self.current_operating_mode = operating_mode

        if row is None:
            self._detector.reset()  # sensor unavailable -> discard the in-progress period
            self._notify_listeners()
            return

        # Pause optimization ticks until an explicit "heat"/"cool" mode is provided.
        if operating_mode is None:
            self._detector.reset()
            self._notify_listeners()
            return

        # Ignore samples when the compressor is below its minimum operating frequency
        # (e.g. standby / defrost).  The flow meter may not count reliably and the
        # COP measurement would be meaningless.
        compressor_freq = row[CONF_COMPRESSOR_FREQUENCY]
        if compressor_freq < self._min_compressor_frequency:
            self._detector.reset()
            return

        cop = calculate_cop_for_row(row, default_mode=operating_mode)
        if math.isnan(cop):
            return

        spread_error = calculate_spread_error_for_row(row, default_mode=operating_mode)
        if math.isnan(spread_error):
            return

        # Compute and store individual ΔT values for sensors.
        # Reset first so sensors reflect None when the mode is unresolvable.
        self.last_primary_delta_t = None
        self.last_secondary_delta_t = None
        _mode = resolve_mode(operating_mode)
        if _mode is not None:
            self.last_primary_delta_t = calculate_delta_t(
                row["primary_flow_temp"], row["primary_return_temp"], _mode
            )
            self.last_secondary_delta_t = calculate_secondary_delta_t(
                row["secondary_flow_temp"], row["secondary_return_temp"], _mode
            )

        observation = self._detector.observe(
            timestamp=now,
            outdoor_temp=row["outdoor_temp"],
            compressor_frequency=row["compressor_frequency"],
            charge_pump_speed=row[CONF_CHARGE_PUMP_SPEED_INPUT],
            cop=cop,
            spread_error=spread_error,
        )
        if observation is None:
            return

        result = self._learning_engine.process(
            observation,
            error_status=self._read_error_status(),
            operating_mode=operating_mode,
        )
        self.last_result = result
        self.last_observation = observation
        _LOGGER.debug(
            "Learning cycle: phase=%s cell=%s mode=%s",
            result.phase,
            result.cell,
            operating_mode,
        )

        if result.phase is Phase.ACTIVE and result.proposed_charge_pump_speed is not None:
            proposed = result.proposed_charge_pump_speed
            last_written_speed = self._last_written_speed_for_mode(operating_mode)
            # Suppress writes that are smaller than the configured minimum step size.
            if (
                self._min_speed_step_percent > 0
                and last_written_speed is not None
                and abs(proposed - last_written_speed) < self._min_speed_step_percent
            ):
                self._notify_listeners()
                return
            if proposed != last_written_speed:
                # Log the decision before writing if the logger is active.
                if self._decision_logger is not None:
                    cell = result.cell
                    log_entry = build_decision_entry(
                        timestamp=now,
                        operating_mode=operating_mode,
                        outdoor_temp_bin=cell.outdoor_temp_bin,
                        compressor_freq_bin=cell.compressor_freq_bin,
                        previous_speed=last_written_speed,
                        proposed_speed=proposed,
                        spread_error_at_current=observation.spread_error,
                        best_abs_spread_error=cell.best_abs_spread_error,
                        cop_at_current=observation.cop,
                        cop_mean_logged=cell.cop_mean_logged,
                        n_measurements=cell.n_measurements,
                        phase=result.phase.name,
                        controller_step_applied=result.controller_step_applied,
                        controller_in_deadband=result.controller_in_deadband,
                        controller_consecutive_deadband_ticks=result.controller_consecutive_deadband_ticks,
                        deadband_k=self._learning_engine.spread_controller_deadband_k,
                        kp=self._learning_engine.spread_controller_kp,
                        improving=result.improving,
                        is_first_observation=result.is_first_observation,
                    )
                    self._hass.async_create_task(self._decision_logger.async_log(log_entry))
                self._remember_last_written_speed(proposed, operating_mode)
                self._hass.async_create_task(self._async_write_pump_speed(proposed, operating_mode))

        self._notify_listeners()

    def _read_float(self, key: str) -> float | None:
        entity_id = self._entity_map.get(key)
        state = self._hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return None if math.isnan(value) else value

    def _write_dhw_speed(self, speed: float) -> None:
        self._remember_last_written_speed(speed, DHW_MODE)
        self._hass.async_create_task(self._async_write_pump_speed(speed, DHW_MODE))

    def _tick_dhw(self, now: datetime) -> None:
        """Hot-water strategy: hold primary flow at target + offset; standby when compressor is off."""
        if not self.dhw_active:
            self.dhw_active = True
            self._dhw_controller.reset()
            self._detector.reset()
            self._last_dhw_eval = None
        if (
            self._last_dhw_eval is not None
            and (now - self._last_dhw_eval).total_seconds() < self.dhw_control_interval_s
        ):
            return
        self._last_dhw_eval = now

        if self._read_error_status():
            self._dhw_controller.reset()
            self._dhw_standby_written = None
            return

        flow = self._read_float(CONF_PRIMARY_FLOW_TEMP)
        target = self._read_float(CONF_DHW_TARGET_TEMP)
        freq = self._read_float(CONF_COMPRESSOR_FREQUENCY)
        if flow is None or target is None or freq is None:
            return  # missing input: never write

        if freq < self._min_compressor_frequency:
            self._dhw_controller.reset()
            standby = clamp_standby_speed(self.dhw_standby_speed, self._min_charge_pump_speed)
            if self._dhw_standby_written != standby:
                self._dhw_standby_written = standby
                self._write_dhw_speed(standby)
            self._notify_listeners()
            return

        self._dhw_standby_written = None
        current = self._last_written_speed_for_mode(DHW_MODE)
        if current is None:
            current = self._read_float(CONF_CHARGE_PUMP_SPEED_INPUT)
        if current is None:
            return
        proposed = self._dhw_controller.update(flow, target, current)
        if proposed != current:
            self._write_dhw_speed(proposed)
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()

    def _read_entities(self) -> tuple[dict[str, float] | None, str | None]:
        """Read all mapped entities as floats; returns (None, mode) if anything is unavailable.

        The operating mode is always returned (possibly None) even when the numeric
        entity reads fail, so callers can update the mode display independently.
        """
        # Determine operating mode first — it is a string entity, not a float.
        operating_mode = self._read_operating_mode()

        row: dict[str, float] = {}
        for key in REQUIRED_ENTITY_KEYS:
            entity_id = self._entity_map.get(key)
            state = self._hass.states.get(entity_id) if entity_id else None
            if state is None or state.state in ("unknown", "unavailable"):
                return None, operating_mode
            try:
                row[key] = float(state.state)
            except ValueError:
                return None, operating_mode

        return row, operating_mode

    def _read_operating_mode(self) -> str | None:
        """Read the operating mode entity as a raw string and normalise to 'heat'/'cool'."""
        entity_id = self._entity_map.get(CONF_OPERATING_MODE)
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return _resolve_operating_mode(state.state, self._dhw_mode_state)

    def _read_error_status(self) -> bool:
        """Safety fallback input: mapped error-status entity 'on', or a failed pump write, forces Phase A."""
        if self.pump_write_error:
            return True
        entity_id = self._entity_map.get(CONF_ERROR_STATUS)
        if not entity_id:
            return False
        state = self._hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _pump_speed_output_entity(self, mode: str | None) -> str | None:
        mode_key = {
            "heat": CONF_CHARGE_PUMP_SPEED_OUTPUT_HEAT,
            "cool": CONF_CHARGE_PUMP_SPEED_OUTPUT_COOL,
            DHW_MODE: CONF_CHARGE_PUMP_SPEED_OUTPUT_DHW,
        }.get(mode)
        return (mode_key and self._entity_map.get(mode_key)) or self._entity_map.get(
            CONF_CHARGE_PUMP_SPEED_OUTPUT
        )

    def _pump_speed_output_key(self, mode: str | None) -> tuple[str, str]:
        entity_id = self._pump_speed_output_entity(mode)
        return ("entity", entity_id) if entity_id else ("mode", mode or "")

    def _last_written_speed_for_mode(self, mode: str | None) -> float | None:
        return self._last_written_speeds.get(self._pump_speed_output_key(mode))

    def _remember_last_written_speed(self, speed: float, mode: str | None) -> None:
        self._last_written_speeds[self._pump_speed_output_key(mode)] = speed
        self._last_written_speed = speed

    async def _async_write_pump_speed(self, speed: float, mode: str | None = None) -> None:
        """Write the proposed speed to the mapped pump output entity (Phase B only).

        The speed is hard-clamped to the configured minimum before writing so the
        flow meter always sees a reliable flow rate.

        If no output entity is configured (passive-only mode), the write is silently
        skipped.  Any failure (unsupported domain, service-call error) sets
        pump_write_error, which forces Phase A on the next cycle until a write succeeds.
        """
        entity_id = self._pump_speed_output_entity(mode)
        if not entity_id:
            # Passive-only mode — no writable entity configured.
            return
        domain = entity_id.split(".", 1)[0]
        if domain not in ("number", "input_number"):
            _LOGGER.error("Cannot write charge_pump_speed: unsupported entity domain %r", domain)
            self.pump_write_error = True
            return

        # Hard clamp: never write below the minimum charge pump speed.
        clamped_speed = max(speed, self._min_charge_pump_speed)
        if clamped_speed != speed:
            _LOGGER.debug(
                "Charge pump speed clamped from %.1f%% to minimum %.1f%%",
                speed,
                clamped_speed,
            )

        try:
            await self._hass.services.async_call(
                domain, "set_value", {"entity_id": entity_id, "value": clamped_speed}, blocking=True
            )
        except Exception:  # noqa: BLE001 - any failure must trigger the safety fallback, not crash
            _LOGGER.exception("Failed to write charge_pump_speed to %s", entity_id)
            self.pump_write_error = True
        else:
            self.pump_write_error = False
