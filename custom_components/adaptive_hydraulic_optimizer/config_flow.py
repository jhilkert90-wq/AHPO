"""Config flow for Adaptive Hydraulic Pump Optimizer: pick the entities to map."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CHARGE_PUMP_SPEED,
    CONF_COMPRESSOR_FREQUENCY,
    CONF_ELECTRICAL_POWER_TOTAL,
    CONF_ERROR_STATUS,
    CONF_OPERATING_MODE,
    CONF_OUTDOOR_TEMP,
    CONF_PRIMARY_FLOW_RATE,
    CONF_PRIMARY_FLOW_TEMP,
    CONF_PRIMARY_RETURN_TEMP,
    DOMAIN,
)

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["sensor", "input_number", "number"])
)
_WRITABLE_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["number", "input_number"])
)
_BINARY_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRIMARY_FLOW_TEMP): _ENTITY_SELECTOR,
        vol.Required(CONF_PRIMARY_RETURN_TEMP): _ENTITY_SELECTOR,
        vol.Required(CONF_PRIMARY_FLOW_RATE): _ENTITY_SELECTOR,
        vol.Required(CONF_ELECTRICAL_POWER_TOTAL): _ENTITY_SELECTOR,
        vol.Required(CONF_COMPRESSOR_FREQUENCY): _ENTITY_SELECTOR,
        vol.Required(CONF_OUTDOOR_TEMP): _ENTITY_SELECTOR,
        vol.Required(CONF_CHARGE_PUMP_SPEED): _WRITABLE_ENTITY_SELECTOR,
        vol.Optional(CONF_OPERATING_MODE): _ENTITY_SELECTOR,
        vol.Optional(CONF_ERROR_STATUS): _BINARY_ENTITY_SELECTOR,
    }
)


class AhpoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial entity-mapping setup (an Options Flow for tunables follows in Milestone 2)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """First (only, for now) step: let the user pick every mapped entity."""
        if user_input is not None:
            return self.async_create_entry(title="Adaptive Hydraulic Pump Optimizer", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)
