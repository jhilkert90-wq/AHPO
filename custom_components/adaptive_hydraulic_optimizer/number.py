"""Number platform: live-adjustable confidence threshold for the Phase A -> B transition."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.phase_manager import PhaseManager
from .entity_base import ahpo_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    phase_manager: PhaseManager = hass.data[DOMAIN][entry.entry_id]["phase_manager"]
    async_add_entities([AhpoConfidenceThresholdNumber(phase_manager, entry)])


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
