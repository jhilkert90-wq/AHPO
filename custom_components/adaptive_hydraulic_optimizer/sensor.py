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
    return round(result.cell.cop_mean, 2) if result else None


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


def _active_cell_fraction(coordinator: AhpoCoordinator) -> float:
    return round(coordinator.phase_manager.active_cell_fraction() * 100, 1)


SENSOR_DESCRIPTIONS: tuple[AhpoSensorDescription, ...] = (
    AhpoSensorDescription(key="current_cop", name="Current COP", icon="mdi:heat-pump", value_fn=_current_cop),
    AhpoSensorDescription(key="averaged_cop", name="Averaged COP", icon="mdi:heat-pump", value_fn=_averaged_cop),
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
        key="active_cell_fraction",
        name="Active cell fraction",
        icon="mdi:chart-donut",
        native_unit_of_measurement="%",
        value_fn=_active_cell_fraction,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AhpoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    characteristic_map: CharacteristicMap = hass.data[DOMAIN][entry.entry_id]["characteristic_map"]
    phase_manager: PhaseManager = hass.data[DOMAIN][entry.entry_id]["phase_manager"]

    entities: list[SensorEntity] = [
        AhpoSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(AhpoTotalCellCountSensor(coordinator, characteristic_map, entry))
    entities.append(AhpoPassiveCellCountSensor(coordinator, characteristic_map, phase_manager, entry))
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
    """Total number of learned characteristic-map cells."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Total map cells"
    _attr_icon = "mdi:grid"
    _attr_native_unit_of_measurement = "cells"

    def __init__(
        self,
        coordinator: AhpoCoordinator,
        characteristic_map: CharacteristicMap,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._characteristic_map = characteristic_map
        self._attr_unique_id = f"{entry.entry_id}_total_cell_count"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> int:
        return len(self._characteristic_map.all_cells())

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
        characteristic_map: CharacteristicMap,
        phase_manager: PhaseManager,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._characteristic_map = characteristic_map
        self._phase_manager = phase_manager
        self._attr_unique_id = f"{entry.entry_id}_passive_cell_count"
        self._attr_device_info = ahpo_device_info(entry)

    @property
    def native_value(self) -> int:
        cells = self._characteristic_map.all_cells()
        return sum(1 for cell in cells if self._phase_manager.get_phase(cell) == Phase.PASSIVE)

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)

