"""Tests for cop.py, including required edge cases (DeltaT=0, missing values, flow=0)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from ahpo_sim import config, cop


def test_calculate_delta_t_heating() -> None:
    assert cop.calculate_delta_t(35.0, 30.0, mode=cop.HEATING) == 5.0


def test_calculate_delta_t_cooling() -> None:
    assert cop.calculate_delta_t(12.0, 18.0, mode=cop.COOLING) == 6.0


def test_calculate_delta_t_invalid_mode_raises() -> None:
    with pytest.raises(ValueError):
        cop.calculate_delta_t(35.0, 30.0, mode="unknown")


def test_calculate_thermal_power_normal() -> None:
    result = cop.calculate_thermal_power(flow_rate_l_min=6.8, delta_t_k=2.3)
    expected = 1.163 * 6.8 * 60 * 2.3
    assert result == pytest.approx(expected)


def test_calculate_thermal_power_zero_flow_rate() -> None:
    # Edge case: zero flow rate -> no thermal power, no exception.
    assert cop.calculate_thermal_power(0.0, 5.0) == 0.0


def test_calculate_thermal_power_zero_delta_t() -> None:
    # Edge case: DeltaT = 0 -> no thermal power, no exception.
    assert cop.calculate_thermal_power(10.0, 0.0) == 0.0


def test_calculate_cop_normal() -> None:
    assert cop.calculate_cop(1000.0, 250.0) == pytest.approx(4.0)


def test_calculate_cop_capped_at_max() -> None:
    # Edge case: implausible spikes must be clamped, not passed through.
    assert cop.calculate_cop(100000.0, 100.0) == pytest.approx(config.COP_MAX_PLAUSIBLE)


def test_calculate_cop_zero_electrical_power() -> None:
    # Edge case: division by zero must not raise, result is NaN.
    assert math.isnan(cop.calculate_cop(1000.0, 0.0))


def test_calculate_cop_negative_electrical_power() -> None:
    assert math.isnan(cop.calculate_cop(1000.0, -5.0))


def test_calculate_cop_missing_thermal_power() -> None:
    # Edge case: missing values (NaN) propagate without raising.
    assert math.isnan(cop.calculate_cop(math.nan, 250.0))


def test_calculate_cop_missing_electrical_power() -> None:
    assert math.isnan(cop.calculate_cop(1000.0, math.nan))


@pytest.mark.parametrize(
    "code,expected",
    [
        (30, cop.HEATING),
        (30.0, cop.HEATING),
        (60, cop.COOLING),
        (10, None),
        (20, None),
        (999, None),
        (None, None),
        (math.nan, None),
    ],
)
def test_resolve_mode(code, expected) -> None:
    assert cop.resolve_mode(code) == expected


def test_calculate_cop_for_row_heating() -> None:
    row = pd.Series(
        {
            "primary_flow_temp": 35.0,
            "primary_return_temp": 30.0,
            "primary_flow_rate": 10.0,
            "electrical_power_total": 500.0,
            "operating_mode": 30.0,
        }
    )
    assert cop.calculate_cop_for_row(row) > 0


def test_calculate_cop_for_row_cooling() -> None:
    row = pd.Series(
        {
            "primary_flow_temp": 12.0,
            "primary_return_temp": 18.0,
            "primary_flow_rate": 10.0,
            "electrical_power_total": 500.0,
            "operating_mode": 60.0,
        }
    )
    assert cop.calculate_cop_for_row(row) > 0


def test_calculate_cop_for_row_off_mode_returns_nan() -> None:
    row = pd.Series(
        {
            "primary_flow_temp": 35.0,
            "primary_return_temp": 30.0,
            "primary_flow_rate": 10.0,
            "electrical_power_total": 500.0,
            "operating_mode": 10.0,
        }
    )
    assert math.isnan(cop.calculate_cop_for_row(row, default_mode=None))

