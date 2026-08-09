"""Sensor platform: read-only output values from the learning engine."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AhpoCoordinator
from .core.characteristic_map import CharacteristicMap
from .core.phase_manager import Phase, PhaseManager
from .entity_base import ahpo_device_info


@dataclass(frozen=True, kw_only=True)
class AhpoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[AhpoCoordinator], float | str | None]


def _current_cop(coordinator: AhpoCoordinator) -> float | None:
    observation = coordinator.last_observation
    return round(observation.cop, 2) if observation else None


def _averaged_cop(coordinator: AhpoCoordinator) -> float | None:
    result = coordinator.last_result
    return round(result.cell.cop_mean_logged, 2) if result else None


def _current_spread_error(coordinator: AhpoCoordinator) -> float | None:
    observation = coordinator.last_observation
    return round(observation.spread_error, 3) if observation else None


def _optimal_charge_pump_speed(coordinator: AhpoCoordinator) -> float | None:
    result = coordinator.last_result
    if result is None or result.cell.optimal_charge_pump_speed is None:
        return None
    return round(result.cell.optimal_charge_pump_speed, 1)


def _confidence_score(coordinator: AhpoCoordinator) -> float | None:
    result = coordinator.last_result
    return round(result.cell.confidence_score, 3) if result else None


def _operating_phase(coordinator: AhpoCoordinator) -> str | None:
    result = coordinator.last_result
    return result.phase.value if result else None


def _operating_mode(coordinator: AhpoCoordinator) -> str | None:
    return coordinator.current_operating_mode


def _primary_delta_t(coordinator: AhpoCoordinator) -> float | None:
    v = coordinator.last_primary_delta_t
    return round(v, 3) if v is not None else None


def _secondary_delta_t(coordinator: AhpoCoordinator) -> float | None:
    v = coordinator.last_secondary_delta_t
    return round(v, 3) if v is not None else None


def _controller_status(coordinator: AhpoCoordinator) -> str | None:
    result = coordinator.last_result
    if result is None or result.phase.name != "ACTIVE":
        return None
    return "haltend" if result.controller_in_deadband else "regelnd"


def _controller_step_applied(coordinator: AhpoCoordinator) -> float | None:
    result = coordinator.last_result
    if result is None or result.phase.name != "ACTIVE":
        return None
    return round(result.controller_step_applied, 2)


def _controller_deadband_ticks_minutes(coordinator: AhpoCoordinator) -> float | None:
    result = coordinator.last_result
    if result is None or result.phase.name != "ACTIVE" or not result.controller_in_deadband:
        return None
    # Each tick corresponds to coordinator.averaging_time_minutes of settled data.
    averaging_minutes = coordinator.averaging_time_minutes
    return round(result.controller_consecutive_deadband_ticks * averaging_minutes, 1)


SENSOR_DESCRIPTIONS: tuple[AhpoSensorDescription, ...] = (
    AhpoSensorDescription(
        key="current_spread_error",
        name="Regelabweichung (Spread error)",
        icon="mdi:delta",
        native_unit_of_measurement="K",
        value_fn=_current_spread_error,
    ),
    AhpoSensorDescription(key="current_cop", name="Current COP (log)", icon="mdi:heat-pump", value_fn=_current_cop),
    AhpoSensorDescription(key="averaged_cop", name="Averaged COP (log)", icon="mdi:heat-pump", value_fn=_averaged_cop),
    AhpoSensorDescription(
        key="optimal_charge_pump_speed",
        name="Optimal charge pump speed",
        icon="mdi:pump",
        native_unit_of_measurement="%",
        value_fn=_optimal_charge_pump_speed,
    ),
    AhpoSensorDescription(
        key="confidence_score", name="Confidence score", icon="mdi:gauge", value_fn=_confidence_score
    ),
    AhpoSensorDescription(
        key="operating_phase", name="Operating phase", icon="mdi:state-machine", value_fn=_operating_phase
    ),
    AhpoSensorDescription(
        key="operating_mode",
        name="Operating mode",
        icon="mdi:thermostat",
        value_fn=_operating_mode,
    ),
    AhpoSensorDescription(
        key="primary_delta_t",
        name="Delta T Primär",
        icon="mdi:thermometer-chevron-up",
        native_unit_of_measurement="K",
        value_fn=_primary_delta_t,
    ),
    AhpoSensorDescription(
        key="secondary_delta_t",
        name="Delta T Sekundär",
        icon="mdi:thermometer-chevron-down",
        native_unit_of_measurement="K",
        value_fn=_secondary_delta_t,
    ),
    AhpoSensorDescription(
        key="controller_status",
        name="Regler-Status",
        icon="mdi:play-pause",
        value_fn=_controller_status,
    ),
    AhpoSensorDescription(
        key="controller_step_applied",
        name="Letzter Regelschritt",
        icon="mdi:stairs",
        native_unit_of_measurement="%",
        value_fn=_controller_step_applied,
    ),
    AhpoSensorDescription(
        key="controller_deadband_minutes",
        name="Zeit in Totzone",
        icon="mdi:timer-pause",
        native_unit_of_measurement="min",
        value_fn=_controller_deadband_ticks_minutes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AhpoCoordinator = data["coordinator"]
    cool_map: CharacteristicMap = data["cool_map"]
    heat_map: CharacteristicMap = data["heat_map"]
    phase_manager: PhaseManager = data["phase_manager"]

    entities: list[SensorEntity] = [
        AhpoSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(AhpoTotalCellCountSensor(coordinator, cool_map, heat_map, entry))
    entities.append(AhpoPassiveCellCountSensor(coordinator, cool_map, heat_map, phase_manager, entry))
    entities.append(AhpoActiveCellFractionSensor(coordinator, cool_map, heat_map, phase_manager, entry))
    async_add_entities(entities)


class AhpoSensor(SensorEntity):
    """Generic push-updated sensor driven by an AhpoSensorDescription.value_fn."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    entity_description: AhpoSensorDescription

    def __init__(
        self, coordinator: AhpoCoordinator, entry: ConfigEntry, description: AhpoSensorDescription
    ) -> None:
        self.entity_description = description
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self._coordinator)

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)


class AhpoTotalCellCountSensor(SensorEntity):
    """Total number of learned characteristic-map cells across both cool and heat maps."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Total map cells"
    _attr_icon = "mdi:grid"
    _attr_native_unit_of_measurement = "cells"

    def __init__(
        self,
        coordinator: AhpoCoordinator,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._attr_unique_id = f"{entry.entry_id}_total_cell_count"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> int:
        return len(self._cool_map.all_cells()) + len(self._heat_map.all_cells())

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)


class AhpoPassiveCellCountSensor(SensorEntity):
    """Number of characteristic-map cells still in passive (Phase A) learning mode."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Passive map cells"
    _attr_icon = "mdi:grid-off"
    _attr_native_unit_of_measurement = "cells"

    def __init__(
        self,
        coordinator: AhpoCoordinator,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
        phase_manager: PhaseManager,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._phase_manager = phase_manager
        self._attr_unique_id = f"{entry.entry_id}_passive_cell_count"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> int:
        all_cells = self._cool_map.all_cells() + self._heat_map.all_cells()
        return sum(1 for cell in all_cells if self._phase_manager.get_phase(cell) == Phase.PASSIVE)

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)


class AhpoActiveCellFractionSensor(SensorEntity):
    """Percentage of characteristic-map cells currently in active (Phase B) mode across both maps."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Active cell fraction"
    _attr_icon = "mdi:chart-donut"
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: AhpoCoordinator,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
        phase_manager: PhaseManager,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._phase_manager = phase_manager
        self._attr_unique_id = f"{entry.entry_id}_active_cell_fraction"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> float:
        all_cells = self._cool_map.all_cells() + self._heat_map.all_cells()
        if not all_cells:
            return 0.0
        active = sum(1 for cell in all_cells if self._phase_manager.get_phase(cell) == Phase.ACTIVE)
        return round(active / len(all_cells) * 100, 1)

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)
