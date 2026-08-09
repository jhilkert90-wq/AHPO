"""Number platform: live-adjustable confidence threshold and P-controller parameters."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.phase_manager import PhaseManager
from .entity_base import ahpo_device_info
from .learning import LearningEngine


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    phase_manager: PhaseManager = data["phase_manager"]
    learning_engine: LearningEngine = data["learning_engine"]
    async_add_entities([
        AhpoConfidenceThresholdNumber(phase_manager, entry),
        AhpoSpreadControllerKpNumber(learning_engine, entry),
        AhpoSpreadControllerDeadbandNumber(learning_engine, entry),
    ])


class AhpoConfidenceThresholdNumber(NumberEntity):
    """Confidence score a cell must reach before it is released for Phase B."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Confidence threshold"
    _attr_icon = "mdi:gauge"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1.0
    _attr_native_step = 0.05

    def __init__(self, phase_manager: PhaseManager, entry: ConfigEntry) -> None:
        self._phase_manager = phase_manager
        self._attr_unique_id = f"{entry.entry_id}_confidence_threshold"
        self._attr_native_value = phase_manager.confidence_threshold
        self._attr_device_info = ahpo_device_info(entry)

    async def async_set_native_value(self, value: float) -> None:
        self._phase_manager.confidence_threshold = value
        self._attr_native_value = value
        self.async_write_ha_state()


class AhpoSpreadControllerKpNumber(NumberEntity):
    """Proportional gain Kp (%/K) of the spread-error P-controller — tunable live."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Kp (aktiv)"
    _attr_icon = "mdi:knob"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 20.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "%/K"

    def __init__(self, learning_engine: LearningEngine, entry: ConfigEntry) -> None:
        self._learning_engine = learning_engine
        self._attr_unique_id = f"{entry.entry_id}_spread_controller_kp"
        self._attr_native_value = learning_engine.spread_controller_kp
        self._attr_device_info = ahpo_device_info(entry)

    async def async_set_native_value(self, value: float) -> None:
        self._learning_engine.spread_controller_kp = value
        self._attr_native_value = value
        self.async_write_ha_state()


class AhpoSpreadControllerDeadbandNumber(NumberEntity):
    """Deadband (K) of the spread-error P-controller — tunable live."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Totzone (Deadband)"
    _attr_icon = "mdi:minus-circle-outline"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 5.0
    _attr_native_step = 0.05
    _attr_native_unit_of_measurement = "K"

    def __init__(self, learning_engine: LearningEngine, entry: ConfigEntry) -> None:
        self._learning_engine = learning_engine
        self._attr_unique_id = f"{entry.entry_id}_spread_controller_deadband_k"
        self._attr_native_value = learning_engine.spread_controller_deadband_k
        self._attr_device_info = ahpo_device_info(entry)

    async def async_set_native_value(self, value: float) -> None:
        self._learning_engine.spread_controller_deadband_k = value
        self._attr_native_value = value
        self.async_write_ha_state()
