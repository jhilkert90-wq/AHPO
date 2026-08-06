"""Constants for the Adaptive Hydraulic Pump Optimizer integration."""
from __future__ import annotations

DOMAIN = "adaptive_hydraulic_optimizer"
PLATFORMS: list[str] = ["sensor", "select", "number", "button"]

# --- Config entry keys: required entity mapping (mirrors ahpo_sim's field mapping) ---
CONF_PRIMARY_FLOW_TEMP = "primary_flow_temp"
CONF_PRIMARY_RETURN_TEMP = "primary_return_temp"
CONF_PRIMARY_FLOW_RATE = "primary_flow_rate"
CONF_ELECTRICAL_POWER_TOTAL = "electrical_power_total"
CONF_COMPRESSOR_FREQUENCY = "compressor_frequency"
CONF_OUTDOOR_TEMP = "outdoor_temp"
CONF_CHARGE_PUMP_SPEED = "charge_pump_speed"  # legacy key — kept for migration only
CONF_CHARGE_PUMP_SPEED_INPUT = "charge_pump_speed_input"   # read-only: measured speed sensor
CONF_CHARGE_PUMP_SPEED_OUTPUT = "charge_pump_speed_output"  # writable: setpoint entity (optional)

REQUIRED_ENTITY_KEYS = (
    CONF_PRIMARY_FLOW_TEMP,
    CONF_PRIMARY_RETURN_TEMP,
    CONF_PRIMARY_FLOW_RATE,
    CONF_ELECTRICAL_POWER_TOTAL,
    CONF_COMPRESSOR_FREQUENCY,
    CONF_OUTDOOR_TEMP,
    CONF_CHARGE_PUMP_SPEED_INPUT,
)

# --- Config entry keys: optional entity mapping ---
CONF_OPERATING_MODE = "operating_mode"
CONF_ERROR_STATUS = "error_status"

OPTIONAL_ENTITY_KEYS = (CONF_OPERATING_MODE, CONF_ERROR_STATUS)

# --- Options (tunable at runtime via the Options Flow, added in Milestone 2) ---
OPT_CONFIDENCE_THRESHOLD = "confidence_threshold"
OPT_CONFIDENCE_MIN_SAMPLES = "confidence_min_samples"
OPT_CONFIDENCE_MAX_COP_STD = "confidence_max_cop_std"
OPT_CONFIDENCE_AGE_HALFLIFE_DAYS = "confidence_age_halflife_days"
OPT_SETTLING_TIME_MINUTES = "settling_time_minutes"
OPT_AVERAGING_TIME_MINUTES = "averaging_time_minutes"
OPT_CHARGE_PUMP_STEP_PERCENT = "charge_pump_step_percent"
OPT_CHARGE_PUMP_STEP_PERCENT_COARSE = "charge_pump_step_percent_coarse"
OPT_MIN_COMPRESSOR_FREQUENCY_HZ = "min_compressor_frequency_hz"
OPT_MIN_CHARGE_PUMP_SPEED_PERCENT = "min_charge_pump_speed_percent"
OPT_DECISION_LOG_ENABLED = "decision_log_enabled"

DEFAULT_OPTIONS: dict[str, float] = {
    OPT_CONFIDENCE_THRESHOLD: 0.7,
    OPT_CONFIDENCE_MIN_SAMPLES: 5,
    OPT_CONFIDENCE_MAX_COP_STD: 1.0,
    OPT_CONFIDENCE_AGE_HALFLIFE_DAYS: 30.0,
    OPT_SETTLING_TIME_MINUTES: 3.0,
    OPT_AVERAGING_TIME_MINUTES: 5.0,
    OPT_CHARGE_PUMP_STEP_PERCENT: 1.0,
    OPT_CHARGE_PUMP_STEP_PERCENT_COARSE: 5.0,
    OPT_MIN_COMPRESSOR_FREQUENCY_HZ: 20.0,
    OPT_MIN_CHARGE_PUMP_SPEED_PERCENT: 15.0,
    OPT_DECISION_LOG_ENABLED: False,
}

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_characteristic_map"
