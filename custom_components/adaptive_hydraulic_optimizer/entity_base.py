"""Shared helpers for AHPO entities."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def ahpo_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return common DeviceInfo so all AHPO entities appear under one 'AHPO' device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="AHPO",
        manufacturer="AHPO",
        model="Adaptive Hydraulic Pump Optimizer",
    )
