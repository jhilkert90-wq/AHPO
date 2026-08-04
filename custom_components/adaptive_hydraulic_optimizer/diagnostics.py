"""Diagnostics support for support/debugging."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    characteristic_map = data["characteristic_map"]
    coordinator = data["coordinator"]
    return {
        "entity_mapping": dict(entry.data),
        "characteristic_map_cell_count": len(characteristic_map.all_cells()),
        "active_cell_fraction": data["phase_manager"].active_cell_fraction(),
        "last_phase": coordinator.last_result.phase.value if coordinator.last_result else None,
        "pump_write_error": coordinator.pump_write_error,
    }
