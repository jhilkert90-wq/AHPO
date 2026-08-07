"""Tests for simulate.py."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from ahpo_sim import config
from ahpo_sim.simulate import add_cop_column


def test_add_cop_column_dataframe() -> None:
    df = pd.DataFrame(
        {
            "primary_flow_temp": [35.0, 12.0, 35.0],
            "primary_return_temp": [30.0, 18.0, 30.0],
            "primary_flow_rate": [10.0, 10.0, 0.0],
            "electrical_power_total": [500.0, 500.0, 0.0],
            "operating_mode": ["heat", "cool", "heat"],
        }
    )
    result = add_cop_column(df)

    assert list(result.columns[-3:]) == ["delta_t", "thermal_power_w", "cop"]
    assert result.loc[0, "cop"] > 0
    assert result.loc[1, "cop"] > 0
    assert math.isnan(result.loc[2, "cop"])


def test_add_cop_column_caps_extreme_cop() -> None:
    # Edge case: a transient near-zero Pel with normal flow must be capped, not left as an outlier.
    df = pd.DataFrame(
        {
            "primary_flow_temp": [35.0],
            "primary_return_temp": [30.0],
            "primary_flow_rate": [10.0],
            "electrical_power_total": [1.0],
            "operating_mode": ["heat"],
        }
    )
    result = add_cop_column(df)
    assert result.loc[0, "cop"] == pytest.approx(config.COP_MAX_PLAUSIBLE)


def test_add_cop_column_invalid_mode_row_is_skipped() -> None:
    df = pd.DataFrame(
        {
            "primary_flow_temp": [35.0, 35.0],
            "primary_return_temp": [30.0, 30.0],
            "primary_flow_rate": [10.0, 10.0],
            "electrical_power_total": [500.0, 500.0],
            "operating_mode": ["heat", "auto"],
        }
    )
    result = add_cop_column(df)
    assert result.loc[0, "cop"] > 0
    assert math.isnan(result.loc[1, "cop"])


def test_add_cop_column_numeric_modes_remain_supported() -> None:
    df = pd.DataFrame(
        {
            "primary_flow_temp": [35.0, 12.0, 35.0],
            "primary_return_temp": [30.0, 18.0, 30.0],
            "primary_flow_rate": [10.0, 10.0, 10.0],
            "electrical_power_total": [500.0, 500.0, 500.0],
            "operating_mode": [30.0, 60.0, 10.0],
        }
    )
    result = add_cop_column(df)
    assert result.loc[0, "cop"] > 0
    assert result.loc[1, "cop"] > 0
    assert math.isnan(result.loc[2, "cop"])
