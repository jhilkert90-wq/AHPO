"""Diagnostics support for support/debugging."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, STORAGE_KEY


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    characteristic_map = data["characteristic_map"]
    phase_manager = data["phase_manager"]
    coordinator = data["coordinator"]

    # Merge data + options so the diagnostics reflect the active entity mapping.
    entity_mapping = {**entry.data, **entry.options}

    cells = characteristic_map.all_cells()
    storage_path = hass.config.path(f".storage/{STORAGE_KEY}_{entry.entry_id}")

    return {
        "entity_mapping": entity_mapping,
        "storage_path": storage_path,
        "characteristic_map": {
            "total_cell_count": len(cells),
            "active_cell_percentage": round(phase_manager.active_cell_fraction() * 100, 1),
            "cells": [cell.to_dict() for cell in cells],
        },
        "last_phase": coordinator.last_result.phase.value if coordinator.last_result else None,
        "pump_write_error": coordinator.pump_write_error,
    }
