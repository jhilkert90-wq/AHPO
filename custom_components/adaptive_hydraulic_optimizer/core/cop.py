"""COP/EER calculation from primary-side temperatures, flow rate and electrical power."""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

HEATING = "heat"
COOLING = "cool"

HEAT_CAPACITY_FACTOR_WH_PER_L_K: float = 1.163  # water, Wh/(l*K)
COP_MAX_PLAUSIBLE: float = 10.0  # cap for implausible spikes (sensor noise/transients)

OPERATING_MODE_OFF = 10
OPERATING_MODE_DHW = 20
OPERATING_MODE_HEATING = 30
OPERATING_MODE_COOLING = 60

OPERATING_MODE_CODES: dict[int, str] = {
    OPERATING_MODE_OFF: "off",
    OPERATING_MODE_DHW: "dhw",
    OPERATING_MODE_HEATING: HEATING,
    OPERATING_MODE_COOLING: COOLING,
}


def _is_missing(value: float | None) -> bool:
    """True for None or NaN, without requiring pandas."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def calculate_delta_t(flow_temp: float, return_temp: float, mode: str = HEATING) -> float:
    """Return the primary-side temperature spread for the given operating mode."""
    if mode not in (HEATING, COOLING):
        raise ValueError(f"Unknown mode: {mode!r} (expected {HEATING!r} or {COOLING!r})")
    return abs(flow_temp - return_temp)


def calculate_thermal_power(flow_rate_l_min: float, delta_t_k: float) -> float:
    """Thermal power in Watts: Q = 1.163 Wh/(l*K) * flow[l/h] * dT[K]."""
    flow_rate_l_h = flow_rate_l_min * 60.0
    return HEAT_CAPACITY_FACTOR_WH_PER_L_K * flow_rate_l_h * delta_t_k


def calculate_cop(thermal_power_w: float, electrical_power_w: float) -> float:
    """COP = Q / Pel, capped at COP_MAX_PLAUSIBLE. Returns NaN for missing/non-positive Pel."""
    if _is_missing(thermal_power_w) or _is_missing(electrical_power_w):
        return math.nan
    if electrical_power_w <= 0:
        _LOGGER.warning(
            "electrical_power_total <= 0 (%.3f W); returning NaN COP", electrical_power_w
        )
        return math.nan
    cop = thermal_power_w / electrical_power_w
    if cop > COP_MAX_PLAUSIBLE:
        _LOGGER.warning("COP %.2f exceeds plausible cap; clamping to %.2f", cop, COP_MAX_PLAUSIBLE)
        return COP_MAX_PLAUSIBLE
    return cop


def resolve_mode(operating_mode_code: float | int | str | None) -> str | None:
    """Map a raw operating-mode value to 'heat'/'cool', else None."""
    if operating_mode_code is None:
        return None
    if isinstance(operating_mode_code, str):
        mode = operating_mode_code.strip().lower()
        return mode if mode in (HEATING, COOLING) else None
    if _is_missing(operating_mode_code):
        return None
    try:
        mode_code = int(operating_mode_code)
    except (TypeError, ValueError):
        return None
    mode = OPERATING_MODE_CODES.get(mode_code)
    return mode if mode in (HEATING, COOLING) else None


def calculate_cop_for_row(row: Mapping[str, float], default_mode: str | None = None) -> float:
    """Calculate COP for a single observation of logical signal values."""
    mode = resolve_mode(row.get("operating_mode")) or default_mode
    if mode not in (HEATING, COOLING):
        return math.nan
    delta_t = calculate_delta_t(row["primary_flow_temp"], row["primary_return_temp"], mode)
    thermal_power = calculate_thermal_power(row["primary_flow_rate"], delta_t)
    return calculate_cop(thermal_power, row["electrical_power_total"])
