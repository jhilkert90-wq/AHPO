"""Tests for timing.py (settling/averaging steady-period detection)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ahpo_sim import config, timing


def _make_df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """rows: (timestamp, outdoor_temp, compressor_frequency, charge_pump_speed, cop)."""
    index = pd.to_datetime([row[0] for row in rows])
    return pd.DataFrame(
        {
            "outdoor_temp": [row[1] for row in rows],
            "compressor_frequency": [row[2] for row in rows],
            "charge_pump_speed": [row[3] for row in rows],
            "cop": [row[4] for row in rows],
        },
        index=index,
    )


def test_empty_input_returns_empty_with_columns() -> None:
    df = _make_df([])
    result = timing.build_stable_observations(df)
    assert result.empty
    assert list(result.columns) == list(timing.REQUIRED_COLUMNS)


def test_short_period_is_dropped() -> None:
    # Edge case: 4 minutes < settling(3) + averaging(5) = 8 minutes -> dropped entirely.
    df = _make_df(
        [
            ("2026-01-01T00:00:00Z", 5.0, 40.0, 30.0, 4.0),
            ("2026-01-01T00:02:00Z", 5.0, 40.0, 30.0, 4.0),
            ("2026-01-01T00:04:00Z", 5.0, 40.0, 30.0, 4.0),
        ]
    )
    result = timing.build_stable_observations(df)
    assert result.empty


def test_period_at_exact_boundary_is_included() -> None:
    # Edge case: exactly settling+averaging (8 min) must be included, not excluded.
    timestamps = [f"2026-01-01T00:{minute:02d}:00Z" for minute in range(0, 9, 2)]
    rows = [(ts, 5.0, 40.0, 30.0, 4.0) for ts in timestamps]
    result = timing.build_stable_observations(_make_df(rows))
    assert len(result) == 1
    assert result.iloc[0]["cop"] == 4.0


def test_averages_only_the_post_settling_window() -> None:
    timestamps = [f"2026-01-01T00:{minute:02d}:00Z" for minute in range(0, 9, 2)]
    # cop before minute 3 (settling) should be excluded from the average.
    cops = [1000.0, 1000.0, 8.0, 10.0, 6.0]
    rows = list(zip(timestamps, [5.0] * 5, [40.0] * 5, [30.0] * 5, cops))
    result = timing.build_stable_observations(_make_df(rows))
    assert len(result) == 1
    assert result.iloc[0]["cop"] == pytest_approx_mean([8.0, 10.0, 6.0])


def pytest_approx_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def test_time_gap_splits_group() -> None:
    # Edge case: a gap bigger than MAX_SAMPLE_GAP_MINUTES must break the steady period.
    early = [f"2026-01-01T00:{minute:02d}:00Z" for minute in range(0, 9, 2)]
    late = [f"2026-01-01T01:{minute:02d}:00Z" for minute in range(0, 9, 2)]
    rows = [(ts, 5.0, 40.0, 30.0, 4.0) for ts in early + late]
    result = timing.build_stable_observations(_make_df(rows))
    assert len(result) == 2


def test_speed_jump_beyond_tolerance_splits_group() -> None:
    # Edge case: a pump-speed jump beyond tolerance must break the steady period.
    timestamps = [f"2026-01-01T00:{minute:02d}:00Z" for minute in range(0, 17, 2)]
    speeds = [30.0] * 5 + [50.0] * 4
    rows = list(zip(timestamps, [5.0] * 9, [40.0] * 9, speeds, [4.0] * 9))
    result = timing.build_stable_observations(_make_df(rows))
    assert len(result) == 1
    assert result.iloc[0]["charge_pump_speed"] == 30.0


def test_frequency_jump_beyond_tolerance_splits_group() -> None:
    timestamps = [f"2026-01-01T00:{minute:02d}:00Z" for minute in range(0, 17, 2)]
    frequencies = [40.0] * 5 + [46.0] * 4
    rows = list(zip(timestamps, [5.0] * 9, frequencies, [30.0] * 9, [4.0] * 9))
    result = timing.build_stable_observations(_make_df(rows))
    assert len(result) == 1
    assert result.iloc[0]["compressor_frequency"] == 40.0


def _detector() -> timing.SteadyPeriodDetector:
    return timing.SteadyPeriodDetector(
        settling_minutes=3.0,
        averaging_minutes=5.0,
        max_sample_gap_minutes=10.0,
        speed_tolerance_percent=1.0,
        frequency_tolerance_hz=1.0,
    )


def test_detector_returns_none_before_settling() -> None:
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    for minute in range(0, 3, 1):
        result = detector.observe(start + timedelta(minutes=minute), 5.0, 40.0, 30.0, 4.0)
        assert result is None


def test_detector_emits_after_settling_and_averaging() -> None:
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    result = None
    for minute in range(0, 9):
        cop_value = 1000.0 if minute < 3 else 4.0  # settling-phase values must be excluded
        result = detector.observe(start + timedelta(minutes=minute), 5.0, 40.0, 30.0, cop_value)
    assert result is not None
    assert result.cop == 4.0


def test_detector_emits_again_after_further_averaging_without_resettling() -> None:
    # Confirms the spec's "many confirmed measurements" behavior: a long steady run
    # keeps producing observations every averaging window, not just once.
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    emissions = []
    for minute in range(0, 15):
        result = detector.observe(start + timedelta(minutes=minute), 5.0, 40.0, 30.0, 4.0)
        if result is not None:
            emissions.append(result)
    assert len(emissions) >= 2


def test_detector_resets_on_speed_jump() -> None:
    # Edge case: a pump-speed jump beyond tolerance must restart settling.
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    for minute in range(0, 8):
        detector.observe(start + timedelta(minutes=minute), 5.0, 40.0, 30.0, 4.0)
    jumped = detector.observe(start + timedelta(minutes=8), 5.0, 40.0, 50.0, 4.0)
    assert jumped is None


def test_detector_resets_on_time_gap() -> None:
    # Edge case: a gap bigger than max_sample_gap_minutes must restart settling.
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    detector.observe(start, 5.0, 40.0, 30.0, 4.0)
    after_gap = detector.observe(start + timedelta(minutes=20), 5.0, 40.0, 30.0, 4.0)
    assert after_gap is None


def test_detector_reset_clears_state() -> None:
    detector = _detector()
    start = datetime(2026, 1, 1, 0, 0)
    for minute in range(0, 8):
        detector.observe(start + timedelta(minutes=minute), 5.0, 40.0, 30.0, 4.0)
    detector.reset()
    result = detector.observe(start + timedelta(minutes=8), 5.0, 40.0, 30.0, 4.0)
    assert result is None
