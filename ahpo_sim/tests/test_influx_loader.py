"""Tests for influx_loader.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ahpo_sim import config
from ahpo_sim.influx_loader import DataLoadError, load_data


def test_load_data_renames_and_filters_columns(sample_csv_path: Path) -> None:
    df = load_data(sample_csv_path)

    expected_logical_columns = {
        logical
        for logical, raw in config.INFLUX_FIELD_MAPPING.items()
        if raw is not None
    }
    assert set(df.columns) == expected_logical_columns
    assert "unused_column" not in df.columns
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing


def test_load_data_missing_raw_column_raises(sample_raw_df: pd.DataFrame, tmp_path: Path) -> None:
    broken_df = sample_raw_df.drop(columns=["Pel"])
    path = tmp_path / "broken.csv"
    broken_df.to_csv(path, index=False)

    with pytest.raises(DataLoadError, match="Pel"):
        load_data(path)


def test_load_data_missing_time_column_raises(sample_raw_df: pd.DataFrame, tmp_path: Path) -> None:
    broken_df = sample_raw_df.drop(columns=["time"])
    path = tmp_path / "no_time.csv"
    broken_df.to_csv(path, index=False)

    with pytest.raises(DataLoadError, match="time"):
        load_data(path)


def test_load_data_file_not_found(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.csv"
    with pytest.raises(DataLoadError):
        load_data(missing_path)


def test_validate_mapping_raises_on_missing_mandatory() -> None:
    bad_mapping = dict(config.INFLUX_FIELD_MAPPING)
    bad_mapping["primary_flow_temp"] = None

    with pytest.raises(config.ConfigError, match="primary_flow_temp"):
        config.validate_mapping(bad_mapping)
