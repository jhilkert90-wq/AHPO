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
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_AVERAGING_TIME_MINUTES,
    OPT_CHARGE_PUMP_STEP_PERCENT,
    OPT_CHARGE_PUMP_STEP_PERCENT_COARSE,
    OPT_CONFIDENCE_AGE_HALFLIFE_DAYS,
    OPT_CONFIDENCE_MAX_COP_STD,
    OPT_CONFIDENCE_MIN_SAMPLES,
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DECISION_LOG_ENABLED,
    OPT_MIN_CHARGE_PUMP_SPEED_PERCENT,
    OPT_MIN_COMPRESSOR_FREQUENCY_HZ,
    OPT_SETTLING_TIME_MINUTES,
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


def _number_selector(min_val: float, max_val: float, step: float = 0.1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=min_val, max=max_val, step=step, mode="box")
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


def _settings_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the tunable-settings schema, pre-filled with current or default values."""
    d = {**DEFAULT_OPTIONS, **(defaults or {})}

    def _num(key: str, min_val: float, max_val: float, step: float = 0.1):
        return (
            vol.Required(key, default=d.get(key, DEFAULT_OPTIONS[key])),
            _number_selector(min_val, max_val, step),
        )

    fields = dict([
        _num(OPT_MIN_COMPRESSOR_FREQUENCY_HZ, 0.0, 100.0, 1.0),
        _num(OPT_MIN_CHARGE_PUMP_SPEED_PERCENT, 0.0, 100.0, 1.0),
        _num(OPT_CONFIDENCE_THRESHOLD, 0.0, 1.0, 0.05),
        _num(OPT_CONFIDENCE_MIN_SAMPLES, 1.0, 100.0, 1.0),
        _num(OPT_CONFIDENCE_MAX_COP_STD, 0.1, 10.0, 0.1),
        _num(OPT_CONFIDENCE_AGE_HALFLIFE_DAYS, 1.0, 365.0, 1.0),
        _num(OPT_SETTLING_TIME_MINUTES, 0.5, 60.0, 0.5),
        _num(OPT_AVERAGING_TIME_MINUTES, 0.5, 60.0, 0.5),
        _num(OPT_CHARGE_PUMP_STEP_PERCENT, 0.1, 20.0, 0.1),
        _num(OPT_CHARGE_PUMP_STEP_PERCENT_COARSE, 1.0, 50.0, 1.0),
        (
            vol.Required(OPT_DECISION_LOG_ENABLED, default=bool(d.get(OPT_DECISION_LOG_ENABLED, False))),
            selector.BooleanSelector(),
        ),
    ])
    return vol.Schema(fields)


STEP_USER_SCHEMA = _entity_mapping_schema()


class AhpoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial entity-mapping setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._entity_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """First step: let the user pick every mapped entity."""
        if user_input is not None:
            self._entity_data = user_input
            return await self.async_step_settings()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        """Second step: configure all tunable algorithm parameters."""
        if user_input is not None:
            return self.async_create_entry(
                title="Adaptive Hydraulic Pump Optimizer",
                data=self._entity_data,
                options=user_input,
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(),
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "AhpoOptionsFlow":
        """Return the options flow handler."""
        return AhpoOptionsFlow(config_entry)


class AhpoOptionsFlow(config_entries.OptionsFlow):
    """Allow editing the entity mapping and algorithm settings after initial setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._entity_data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Step 1: Show the entity-mapping form pre-filled with current values."""
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            self._entity_data = user_input
            return await self.async_step_settings()

        return self.async_show_form(
            step_id="init",
            data_schema=_entity_mapping_schema(current),
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        """Step 2: Show the algorithm-settings form pre-filled with current options."""
        current_opts = {**DEFAULT_OPTIONS, **self._config_entry.options}

        if user_input is not None:
            # Merge entity mapping back with the new settings into options only.
            return self.async_create_entry(data={**self._entity_data, **user_input})

        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(current_opts),
        )

