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

    def _req(key: str, selector_obj):
        return vol.Required(key, default=d.get(key, vol.UNDEFINED)), selector_obj

    def _opt(key: str, selector_obj):
        return vol.Optional(key, default=d.get(key, vol.UNDEFINED)), selector_obj

    fields = dict([
        _req(CONF_PRIMARY_FLOW_TEMP, _ENTITY_SELECTOR),
        _req(CONF_PRIMARY_RETURN_TEMP, _ENTITY_SELECTOR),
        _req(CONF_PRIMARY_FLOW_RATE, _ENTITY_SELECTOR),
        _req(CONF_ELECTRICAL_POWER_TOTAL, _ENTITY_SELECTOR),
        _req(CONF_COMPRESSOR_FREQUENCY, _ENTITY_SELECTOR),
        _req(CONF_OUTDOOR_TEMP, _ENTITY_SELECTOR),
        _req(CONF_CHARGE_PUMP_SPEED_INPUT, _ENTITY_SELECTOR),
        _opt(CONF_CHARGE_PUMP_SPEED_OUTPUT, _WRITABLE_ENTITY_SELECTOR),
        _opt(CONF_OPERATING_MODE, _ENTITY_SELECTOR),
        _opt(CONF_ERROR_STATUS, _BINARY_ENTITY_SELECTOR),
    ])
    return vol.Schema(fields)


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
