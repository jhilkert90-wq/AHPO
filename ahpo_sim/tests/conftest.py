"""Shared pytest fixtures for ahpo_sim tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def sample_raw_df() -> pd.DataFrame:
    """Minimal raw dataset using the real InfluxDB export column names."""
    return pd.DataFrame(
        {
            "time": [
                "2026-05-01T00:00:58.922203Z",
                "2026-05-01T00:02:58.919332Z",
                "2026-05-01T00:04:58.911380Z",
            ],
            "AT": [4.3, 4.3, 4.3],
            "Hz": [20.0, 20.0, 20.0],
            "Pel": [382.0, 382.0, 382.0],
            "KTe": [26.7, 26.7, 26.7],
            "KTa": [24.4, 24.4, 24.4],
            "Vol": [6.8, 6.8, 6.8],
            "KT%": [30.0, 30.0, 30.0],
            "BM": [30.0, 30.0, 30.0],
            "unused_column": [1, 2, 3],
        }
    )


@pytest.fixture
def sample_csv_path(tmp_path: Path, sample_raw_df: pd.DataFrame) -> Path:
    path = tmp_path / "sample.csv"
    sample_raw_df.to_csv(path, index=False)
    return path
