"""Load historical AHPO sensor data and normalize columns to logical names.

All raw InfluxDB/CSV column names are resolved exclusively through
config.INFLUX_FIELD_MAPPING; downstream code must only see logical names.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

TIME_COLUMN = "time"


class DataLoadError(RuntimeError):
    """Raised when the raw data file cannot be loaded or is missing required columns."""


def _raw_to_logical_mapping() -> dict[str, str]:
    """Inverse of INFLUX_FIELD_MAPPING, excluding unmapped (None) optional fields."""
    return {
        raw_name: logical_name
        for logical_name, raw_name in config.INFLUX_FIELD_MAPPING.items()
        if raw_name is not None
    }


def load_data(csv_path: str | Path | None = None) -> pd.DataFrame:
    """Load the historical dataset and rename columns to logical signal names.

    Returns a time-indexed, chronologically sorted DataFrame containing only
    the logical columns from INFLUX_FIELD_MAPPING (raw columns are dropped).
    """
    path = Path(csv_path) if csv_path is not None else Path(config.CSV_PATH)
    if not path.is_file():
        raise DataLoadError(f"Data file not found: {path}")

    logger.info("Loading historical data from %s", path)
    df = pd.read_csv(path)

    if TIME_COLUMN not in df.columns:
        raise DataLoadError(f"Expected a '{TIME_COLUMN}' column in {path}.")

    raw_to_logical = _raw_to_logical_mapping()
    missing_columns = [raw for raw in raw_to_logical if raw not in df.columns]
    if missing_columns:
        raise DataLoadError(
            "The following mapped columns are missing from the data file "
            f"{path}: {missing_columns}. Check INFLUX_FIELD_MAPPING in config.py."
        )

    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], utc=True)
    df = df.set_index(TIME_COLUMN).sort_index()
    df = df.rename(columns=raw_to_logical)
    df = df[list(raw_to_logical.values())]

    logger.info("Loaded %d rows, %d logical columns", len(df), df.shape[1])
    return df
