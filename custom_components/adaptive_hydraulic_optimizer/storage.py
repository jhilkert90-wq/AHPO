"""Persistence for the characteristic map via Home Assistant's Store helper."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .core.characteristic_map import CharacteristicMap


class CharacteristicMapStore:
    """Thin wrapper around HA's Store, (de)serializing via CharacteristicMap.to_dict()/from_dict()."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[list[dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}"
        )

    async def async_load(self, characteristic_map: CharacteristicMap) -> None:
        """Populate characteristic_map from persisted storage, if any (no-op if none saved yet)."""
        records = await self._store.async_load()
        if records:
            characteristic_map.from_dict(records)

    async def async_save(self, characteristic_map: CharacteristicMap) -> None:
        """Persist the current characteristic map (HA's Store debounces/rate-limits writes)."""
        await self._store.async_save(characteristic_map.to_dict())
