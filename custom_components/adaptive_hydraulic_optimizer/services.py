"""Service registrations for Adaptive Hydraulic Pump Optimizer.

Simplification: services act on all configured entries (this integration is designed
for a single heat pump per Home Assistant instance).
"""
from __future__ import annotations

import json
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .core.phase_manager import Phase

_LOGGER = logging.getLogger(__name__)

SERVICE_RESET_MAP = "reset_characteristic_map"
SERVICE_RESET_CONFIDENCE = "reset_confidence"
SERVICE_SET_PHASE_OVERRIDE = "set_phase_override"
SERVICE_EXPORT_MAP = "export_characteristic_map"

ATTR_PHASE = "phase"
ATTR_PATH = "path"

_OPTION_TO_PHASE: dict[str, Phase | None] = {
    "automatic": None,
    "passive": Phase.PASSIVE,
    "active": Phase.ACTIVE,
}

_PHASE_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_PHASE): vol.In(list(_OPTION_TO_PHASE))})
_EXPORT_SCHEMA = vol.Schema({vol.Required(ATTR_PATH): cv.string})


def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's services once (shared across all config entries)."""

    async def _async_reset_map(call: ServiceCall) -> None:
        for entry_data in hass.data.get(DOMAIN, {}).values():
            entry_data["characteristic_map"].clear()

    async def _async_reset_confidence(call: ServiceCall) -> None:
        for entry_data in hass.data.get(DOMAIN, {}).values():
            for cell in entry_data["characteristic_map"].all_cells():
                cell.confidence_score = 0.0

    async def _async_set_phase_override(call: ServiceCall) -> None:
        phase = _OPTION_TO_PHASE[call.data[ATTR_PHASE]]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            entry_data["phase_manager"].set_global_override(phase)

    async def _async_export_map(call: ServiceCall) -> None:
        path = call.data[ATTR_PATH]
        for entry_data in hass.data.get(DOMAIN, {}).values():
            records = entry_data["characteristic_map"].to_dict()

            def _write(records=records) -> None:
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(records, handle, indent=2)

            await hass.async_add_executor_job(_write)

    hass.services.async_register(DOMAIN, SERVICE_RESET_MAP, _async_reset_map)
    hass.services.async_register(DOMAIN, SERVICE_RESET_CONFIDENCE, _async_reset_confidence)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_PHASE_OVERRIDE, _async_set_phase_override, schema=_PHASE_OVERRIDE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_EXPORT_MAP, _async_export_map, schema=_EXPORT_SCHEMA)


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all services (called once the last config entry is unloaded)."""
    for service in (SERVICE_RESET_MAP, SERVICE_RESET_CONFIDENCE, SERVICE_SET_PHASE_OVERRIDE, SERVICE_EXPORT_MAP):
        hass.services.async_remove(DOMAIN, service)
