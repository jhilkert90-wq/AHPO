"""Central configuration: InfluxDB column mapping and simulation parameters.

No InfluxDB column/field name may be hardcoded anywhere else in this project;
all other modules must only reference the logical names defined as keys of
INFLUX_FIELD_MAPPING below.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- InfluxDB field mapping --------------------------------------------------
# Maps logical signal names (used throughout the rest of the code) to the
# actual raw column/field names present in the InfluxDB export / CSV.
# Set a value to None only for genuinely optional signals.
INFLUX_FIELD_MAPPING: dict[str, str | None] = {
    "primary_flow_temp": "KTe",  # primary-side (condenser) flow temperature
    "primary_return_temp": "KTa",  # primary-side (condenser) return temperature
    "primary_flow_rate": "Vol",  # primary-side flow rate, l/min
    "electrical_power_total": "Pel",  # total electrical power, W
    "compressor_frequency": "Hz",  # compressor frequency, Hz
    "outdoor_temp": "AT",  # outdoor temperature
    "charge_pump_speed": "KT%",  # charge pump speed (actual), %
    "secondary_flow_temp": None,  # TODO: set to the real InfluxDB column name
    "secondary_return_temp": None,  # TODO: set to the real InfluxDB column name
    # optional:
    "operating_mode": "BM",  # operating-mode code, see OPERATING_MODE_CODES
    "primary_pump_state": None,
    "compressor_status": None,
    "error_status": None,
    "external_control_active": None,  # flag/entity for Phase-A detection
}

# Signals that MUST resolve to a real column (value must not be None).
MANDATORY_FIELDS: tuple[str, ...] = (
    "primary_flow_temp",
    "primary_return_temp",
    "primary_flow_rate",
    "electrical_power_total",
    "compressor_frequency",
    "outdoor_temp",
    "charge_pump_speed",
    "secondary_flow_temp",
    "secondary_return_temp",
)

OPTIONAL_FIELDS: tuple[str, ...] = tuple(
    key for key in INFLUX_FIELD_MAPPING if key not in MANDATORY_FIELDS
)


class ConfigError(RuntimeError):
    """Raised when the field mapping or other configuration is invalid."""


def validate_mapping(mapping: dict[str, str | None]) -> None:
    """Fail fast with a clear error instead of a KeyError deep in the pipeline."""
    missing = [field for field in MANDATORY_FIELDS if not mapping.get(field)]
    if missing:
        raise ConfigError(
            "INFLUX_FIELD_MAPPING is missing required (non-optional) fields: "
            f"{missing}. Set a raw column name for each of these in config.py."
        )

# --- Data source --------------------------------------------------------------
# Phase 1 uses a CSV export of historical InfluxDB (v1) data; no live query yet.
DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "sensordaten_2025-06-19_ab.csv"
CSV_PATH: str = os.getenv("AHPO_CSV_PATH", str(DEFAULT_CSV_PATH))

# Kept for a future live-InfluxDB implementation; unused while CSV_PATH is the source.
INFLUX_QUERY = {
    "bucket": os.getenv("INFLUXDB_BUCKET", "TODO"),
    "measurement": os.getenv("INFLUXDB_MEASUREMENT", "TODO"),
    "time_range": ("-90d", "now()"),
}

# --- Operating mode codes (BM field) ------------------------------------------
OPERATING_MODE_OFF = 10
OPERATING_MODE_DHW = 20
OPERATING_MODE_HEATING = 30
OPERATING_MODE_COOLING = 60

OPERATING_MODE_CODES: dict[int, str] = {
    OPERATING_MODE_OFF: "off",
    OPERATING_MODE_DHW: "dhw",
    OPERATING_MODE_HEATING: "heat",
    OPERATING_MODE_COOLING: "cool",
}

# --- Physics constants ---------------------------------------------------------
HEAT_CAPACITY_FACTOR_WH_PER_L_K: float = 1.163  # water, Wh/(l*K)
FLOW_RATE_UNIT: str = "l/min"
COP_MAX_PLAUSIBLE: float = 10.0  # cap for implausible spikes (sensor noise/transients)

# --- Characteristic map grid (used by characteristic_map.py) -------------------
MAP_OUTDOOR_TEMP_STEP_C: float = 2.0
MAP_COMPRESSOR_FREQ_STEP_HZ: float = 2.0

# Compressor frequency below this is treated as idle/cycling, not a real operating
# point, and excluded from characteristic-map/optimizer ingestion (used by simulate.py).
MIN_COMPRESSOR_FREQUENCY_HZ: float = float(os.getenv("AHPO_MIN_COMPRESSOR_FREQUENCY_HZ", "20.0"))

# --- Sanity bounds for raw sensor values (used by simulate.py) -----------------
# Rows outside these ranges are dropped before characteristic-map/optimizer ingestion;
# real installations occasionally report sensor glitches (e.g. outdoor_temp = 3275°C).
OUTDOOR_TEMP_PLAUSIBLE_RANGE_C: tuple[float, float] = (-40.0, 50.0)
CHARGE_PUMP_SPEED_PLAUSIBLE_RANGE_PERCENT: tuple[float, float] = (0.0, 100.0)

# --- Confidence / phase transition (used by phase_manager.py) -----------------
# TODO: refine formula; for now: min sample count + max COP std-dev.
CONFIDENCE_MIN_SAMPLES: int = 5
CONFIDENCE_MAX_SPREAD_ERROR_STD: float = 0.5  # ΔT in Kelvin; 0.5 K is a tighter bound than the old COP-std default
CONFIDENCE_THRESHOLD: float = 0.7  # confidence_score >= this -> cell may move to Phase B
# Confidence decays with data age (exponential half-life); no decay if reference_time is unset.
CONFIDENCE_AGE_HALFLIFE_DAYS: float = 30.0

# --- Optimizer (used by optimizer.py) ------------------------------------------
CHARGE_PUMP_STEP_PERCENT: float = 1.0
CHARGE_PUMP_STEP_PERCENT_COARSE: float = 5.0

# --- Settling/averaging timing model (used by timing.py) -----------------------
# Ablauf Phase A/B: after a speed/frequency change (or once stability is detected),
# wait SETTLING_TIME_MINUTES, then average COP over the following AVERAGING_TIME_MINUTES.
SETTLING_TIME_MINUTES: float = 3.0
AVERAGING_TIME_MINUTES: float = 5.0
MAX_SAMPLE_GAP_MINUTES: float = 10.0  # bigger data gaps break a steady period
CHARGE_PUMP_SPEED_STABILITY_TOLERANCE_PERCENT: float = 2.0
COMPRESSOR_FREQUENCY_STABILITY_TOLERANCE_HZ: float = 2.0

# --- Logging --------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("AHPO_LOG_LEVEL", "INFO")
