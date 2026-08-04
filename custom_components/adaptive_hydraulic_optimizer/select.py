"""Select platform: manual global Phase A/B override."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.phase_manager import Phase, PhaseManager

OPTION_AUTOMATIC = "automatic"
OPTION_PASSIVE = "passive"
OPTION_ACTIVE = "active"

_OPTION_TO_PHASE: dict[str, Phase | None] = {
    OPTION_AUTOMATIC: None,
    OPTION_PASSIVE: Phase.PASSIVE,
    OPTION_ACTIVE: Phase.ACTIVE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    phase_manager: PhaseManager = hass.data[DOMAIN][entry.entry_id]["phase_manager"]
    async_add_entities([AhpoPhaseOverrideSelect(phase_manager, entry)])


class AhpoPhaseOverrideSelect(SelectEntity):
    """Lets the user force Phase A/B globally (e.g. after switching NIBE to manual)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Phase override"
    _attr_options = [OPTION_AUTOMATIC, OPTION_PASSIVE, OPTION_ACTIVE]
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, phase_manager: PhaseManager, entry: ConfigEntry) -> None:
        self._phase_manager = phase_manager
        self._attr_unique_id = f"{entry.entry_id}_phase_override"
        self._attr_current_option = OPTION_AUTOMATIC

    async def async_select_option(self, option: str) -> None:
        self._phase_manager.set_global_override(_OPTION_TO_PHASE[option])
        self._attr_current_option = option
        self.async_write_ha_state()
