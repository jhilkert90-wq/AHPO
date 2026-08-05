"""Persistence for the characteristic map via Home Assistant's Store helper."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .core.characteristic_map import CharacteristicMap

# Top-level keys used inside the single storage file for the two operating modes.
_KEY_COOL = "cool"
_KEY_HEAT = "heat"


class CharacteristicMapStore:
    """Thin wrapper around HA's Store, (de)serializing via CharacteristicMap.to_dict()/from_dict().

    A single JSON file holds both the 'cool' and 'heat' characteristic maps under
    their respective top-level keys so no migration is needed when adding the second map.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}"
        )

    async def async_load(
        self,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
    ) -> None:
        """Populate both maps from persisted storage (no-op if nothing saved yet).

        Legacy files that contain a bare list (single-map format from before the
        cool/heat split) are loaded into *both* maps so existing learned data is
        not lost after the upgrade.
        """
        data = await self._store.async_load()
        if not data:
            return
        if isinstance(data, list):
            # Legacy single-map format: populate both maps with the same records.
            cool_map.from_dict(data)
            heat_map.from_dict(data)
            return
        cool_records = data.get(_KEY_COOL)
        if cool_records:
            cool_map.from_dict(cool_records)
        heat_records = data.get(_KEY_HEAT)
        if heat_records:
            heat_map.from_dict(heat_records)

    async def async_save(
        self,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
    ) -> None:
        """Persist both characteristic maps into one storage file."""
        await self._store.async_save(
            {
                _KEY_COOL: cool_map.to_dict(),
                _KEY_HEAT: heat_map.to_dict(),
            }
        )
