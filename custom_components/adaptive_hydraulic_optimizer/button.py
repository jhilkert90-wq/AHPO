"""Button platform: reset actions for the characteristic map / confidence scores."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.characteristic_map import CharacteristicMap
from .entity_base import ahpo_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    cool_map: CharacteristicMap = entry_data["cool_map"]
    heat_map: CharacteristicMap = entry_data["heat_map"]
    async_add_entities(
        [
            AhpoResetMapButton(cool_map, heat_map, entry),
            AhpoResetConfidenceButton(cool_map, heat_map, entry),
        ]
    )


class AhpoResetMapButton(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Reset characteristic map"
    _attr_icon = "mdi:delete-sweep"

    def __init__(self, cool_map: CharacteristicMap, heat_map: CharacteristicMap, entry: ConfigEntry) -> None:
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._attr_unique_id = f"{entry.entry_id}_reset_map"
        self._attr_device_info = ahpo_device_info(entry)

    async def async_press(self) -> None:
        self._cool_map.clear()
        self._heat_map.clear()


class AhpoResetConfidenceButton(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Reset confidence"
    _attr_icon = "mdi:gauge-empty"

    def __init__(self, cool_map: CharacteristicMap, heat_map: CharacteristicMap, entry: ConfigEntry) -> None:
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._attr_unique_id = f"{entry.entry_id}_reset_confidence"
        self._attr_device_info = ahpo_device_info(entry)

    async def async_press(self) -> None:
        for cell in self._cool_map.all_cells() + self._heat_map.all_cells():
            cell.confidence_score = 0.0
