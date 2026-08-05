"""Adaptive Hydraulic Pump Optimizer: async_setup_entry/async_unload_entry."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_CHARGE_PUMP_SPEED, CONF_CHARGE_PUMP_SPEED_INPUT, DOMAIN, PLATFORMS, REQUIRED_ENTITY_KEYS, STORAGE_KEY
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
    # Prefer options over original data so edits via the Options Flow take effect.
    entity_map = {**entry.data, **entry.options}

    # Migrate legacy charge_pump_speed key to charge_pump_speed_input so existing
    # config entries created before the input/output split continue to work.
    if CONF_CHARGE_PUMP_SPEED in entity_map and CONF_CHARGE_PUMP_SPEED_INPUT not in entity_map:
        entity_map[CONF_CHARGE_PUMP_SPEED_INPUT] = entity_map[CONF_CHARGE_PUMP_SPEED]

    _async_validate_entities(hass, entry, entity_map)

    characteristic_map = CharacteristicMap()
    store = CharacteristicMapStore(hass, entry.entry_id)
    await store.async_load(characteristic_map)

    storage_path = f".storage/{STORAGE_KEY}_{entry.entry_id}"
    _LOGGER.info("AHPO characteristic map stored at: %s", storage_path)

    phase_manager = PhaseManager(characteristic_map)
    learning_engine = LearningEngine(characteristic_map, phase_manager)
    coordinator = AhpoCoordinator(hass, entity_map, learning_engine, phase_manager)
    coordinator.async_start()

    async def _async_save(_now) -> None:
        await store.async_save(characteristic_map)

    unsubscribe_save = async_track_time_interval(hass, _async_save, SAVE_INTERVAL)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "characteristic_map": characteristic_map,
        "phase_manager": phase_manager,
        "coordinator": coordinator,
        "store": store,
        "unsubscribe_save": unsubscribe_save,
    }

    # Register services idempotently — safe to call on every setup.
    async_register_services(hass)

    # Reload the entry automatically when the user saves new options.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_validate_entities(hass: HomeAssistant, entry: ConfigEntry, entity_map: dict) -> None:
    """Fail fast (with an automatic HA retry) instead of silently running with missing entities."""
    missing = [
        key
        for key in REQUIRED_ENTITY_KEYS
        if hass.states.get(entity_map.get(key, "")) is None
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

