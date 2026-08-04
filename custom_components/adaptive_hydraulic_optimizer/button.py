"""Button platform: reset actions for the characteristic map / confidence scores."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.characteristic_map import CharacteristicMap


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    characteristic_map: CharacteristicMap = hass.data[DOMAIN][entry.entry_id]["characteristic_map"]
    async_add_entities(
        [
            AhpoResetMapButton(characteristic_map, entry),
            AhpoResetConfidenceButton(characteristic_map, entry),
        ]
    )


class AhpoResetMapButton(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Reset characteristic map"
    _attr_icon = "mdi:delete-sweep"

    def __init__(self, characteristic_map: CharacteristicMap, entry: ConfigEntry) -> None:
        self._characteristic_map = characteristic_map
        self._attr_unique_id = f"{entry.entry_id}_reset_map"

    async def async_press(self) -> None:
        self._characteristic_map.clear()


class AhpoResetConfidenceButton(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Reset confidence"
    _attr_icon = "mdi:gauge-empty"

    def __init__(self, characteristic_map: CharacteristicMap, entry: ConfigEntry) -> None:
        self._characteristic_map = characteristic_map
        self._attr_unique_id = f"{entry.entry_id}_reset_confidence"

    async def async_press(self) -> None:
        for cell in self._characteristic_map.all_cells():
            cell.confidence_score = 0.0
