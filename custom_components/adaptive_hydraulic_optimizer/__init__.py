"""Adaptive Hydraulic Pump Optimizer: async_setup_entry/async_unload_entry."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PLATFORMS, REQUIRED_ENTITY_KEYS
from .coordinator import AhpoCoordinator
from .core.characteristic_map import CharacteristicMap
from .core.phase_manager import PhaseManager
from .learning import LearningEngine
from .services import async_register_services, async_unregister_services
from .storage import CharacteristicMapStore

_LOGGER = logging.getLogger(__name__)

SAVE_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured heat pump: load the characteristic map, start the coordinator."""
    _async_validate_entities(hass, entry)

    is_first_entry = DOMAIN not in hass.data

    characteristic_map = CharacteristicMap()
    store = CharacteristicMapStore(hass, entry.entry_id)
    await store.async_load(characteristic_map)

    phase_manager = PhaseManager(characteristic_map)
    learning_engine = LearningEngine(characteristic_map, phase_manager)
    coordinator = AhpoCoordinator(hass, dict(entry.data), learning_engine, phase_manager)
    coordinator.async_start()

    unsubscribe_save = async_track_time_interval(
        hass, lambda _now: hass.async_create_task(store.async_save(characteristic_map)), SAVE_INTERVAL
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "characteristic_map": characteristic_map,
        "phase_manager": phase_manager,
        "coordinator": coordinator,
        "store": store,
        "unsubscribe_save": unsubscribe_save,
    }

    if is_first_entry:
        async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _async_validate_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Fail fast (with an automatic HA retry) instead of silently running with missing entities."""
    missing = [
        key
        for key in REQUIRED_ENTITY_KEYS
        if hass.states.get(entry.data.get(key, "")) is None
    ]
    if missing:
        raise ConfigEntryNotReady(f"Mapped entities not yet available: {missing}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the coordinator, persist one last time, and tear down."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id)
    data["coordinator"].async_stop()
    data["unsubscribe_save"]()
    await data["store"].async_save(data["characteristic_map"])

    if not hass.data[DOMAIN]:
        async_unregister_services(hass)

    return True

