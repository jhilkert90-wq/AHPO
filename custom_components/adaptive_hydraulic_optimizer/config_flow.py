"""Config flow for Adaptive Hydraulic Pump Optimizer: pick the entities to map."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CHARGE_PUMP_SPEED_INPUT,
    CONF_CHARGE_PUMP_SPEED_OUTPUT,
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


def _entity_mapping_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the entity-mapping schema, optionally pre-filled with *defaults*."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_PRIMARY_FLOW_TEMP, default=d[CONF_PRIMARY_FLOW_TEMP])
            if CONF_PRIMARY_FLOW_TEMP in d
            else vol.Required(CONF_PRIMARY_FLOW_TEMP): _ENTITY_SELECTOR,
            vol.Required(CONF_PRIMARY_RETURN_TEMP, default=d[CONF_PRIMARY_RETURN_TEMP])
            if CONF_PRIMARY_RETURN_TEMP in d
            else vol.Required(CONF_PRIMARY_RETURN_TEMP): _ENTITY_SELECTOR,
            vol.Required(CONF_PRIMARY_FLOW_RATE, default=d[CONF_PRIMARY_FLOW_RATE])
            if CONF_PRIMARY_FLOW_RATE in d
            else vol.Required(CONF_PRIMARY_FLOW_RATE): _ENTITY_SELECTOR,
            vol.Required(CONF_ELECTRICAL_POWER_TOTAL, default=d[CONF_ELECTRICAL_POWER_TOTAL])
            if CONF_ELECTRICAL_POWER_TOTAL in d
            else vol.Required(CONF_ELECTRICAL_POWER_TOTAL): _ENTITY_SELECTOR,
            vol.Required(CONF_COMPRESSOR_FREQUENCY, default=d[CONF_COMPRESSOR_FREQUENCY])
            if CONF_COMPRESSOR_FREQUENCY in d
            else vol.Required(CONF_COMPRESSOR_FREQUENCY): _ENTITY_SELECTOR,
            vol.Required(CONF_OUTDOOR_TEMP, default=d[CONF_OUTDOOR_TEMP])
            if CONF_OUTDOOR_TEMP in d
            else vol.Required(CONF_OUTDOOR_TEMP): _ENTITY_SELECTOR,
            vol.Required(CONF_CHARGE_PUMP_SPEED_INPUT, default=d[CONF_CHARGE_PUMP_SPEED_INPUT])
            if CONF_CHARGE_PUMP_SPEED_INPUT in d
            else vol.Required(CONF_CHARGE_PUMP_SPEED_INPUT): _ENTITY_SELECTOR,
            vol.Optional(CONF_CHARGE_PUMP_SPEED_OUTPUT, default=d[CONF_CHARGE_PUMP_SPEED_OUTPUT])
            if CONF_CHARGE_PUMP_SPEED_OUTPUT in d
            else vol.Optional(CONF_CHARGE_PUMP_SPEED_OUTPUT): _WRITABLE_ENTITY_SELECTOR,
            vol.Optional(CONF_OPERATING_MODE, default=d[CONF_OPERATING_MODE])
            if CONF_OPERATING_MODE in d
            else vol.Optional(CONF_OPERATING_MODE): _ENTITY_SELECTOR,
            vol.Optional(CONF_ERROR_STATUS, default=d[CONF_ERROR_STATUS])
            if CONF_ERROR_STATUS in d
            else vol.Optional(CONF_ERROR_STATUS): _BINARY_ENTITY_SELECTOR,
        }
    )


STEP_USER_SCHEMA = _entity_mapping_schema()


class AhpoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial entity-mapping setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """First step: let the user pick every mapped entity."""
        if user_input is not None:
            return self.async_create_entry(title="Adaptive Hydraulic Pump Optimizer", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "AhpoOptionsFlow":
        """Return the options flow handler."""
        return AhpoOptionsFlow(config_entry)


class AhpoOptionsFlow(config_entries.OptionsFlow):
    """Allow editing the entity mapping after initial setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options form pre-filled with current values."""
        # Merge data + options so existing choices appear as defaults
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_entity_mapping_schema(current),
        )
