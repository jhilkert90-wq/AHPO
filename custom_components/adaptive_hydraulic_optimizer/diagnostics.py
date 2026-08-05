"""Diagnostics support for support/debugging."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, STORAGE_KEY
from .core.phase_manager import Phase


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    cool_map = data["cool_map"]
    heat_map = data["heat_map"]
    phase_manager = data["phase_manager"]
    coordinator = data["coordinator"]

    # Merge data + options so the diagnostics reflect the active entity mapping.
    entity_mapping = {**entry.data, **entry.options}

    cool_cells = cool_map.all_cells()
    heat_cells = heat_map.all_cells()
    all_cells = cool_cells + heat_cells
    storage_path = f".storage/{STORAGE_KEY}_{entry.entry_id}"

    # Compute active-cell percentage manually across both maps so the fraction
    # is not skewed by PhaseManager only knowing about one of the two maps.
    active_count = sum(
        1 for cell in all_cells if phase_manager.get_phase(cell) == Phase.ACTIVE
    )
    active_pct = round(active_count / len(all_cells) * 100, 1) if all_cells else 0.0

    return {
        "entity_mapping": entity_mapping,
        "storage_path": storage_path,
        "current_operating_mode": coordinator.current_operating_mode,
        "characteristic_map": {
            "total_cell_count": len(all_cells),
            "active_cell_percentage": active_pct,
            "cool": {
                "cell_count": len(cool_cells),
                "cells": [cell.to_dict() for cell in cool_cells],
            },
            "heat": {
                "cell_count": len(heat_cells),
                "cells": [cell.to_dict() for cell in heat_cells],
            },
        },
        "last_phase": coordinator.last_result.phase.value if coordinator.last_result else None,
        "pump_write_error": coordinator.pump_write_error,
    }
