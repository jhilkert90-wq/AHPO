"""Steady-period detection matching the spec's settling/averaging timing model.

After a pump-speed/frequency change (or once stability is detected), wait
SETTLING_TIME_MINUTES for the system to settle, then average COP over the
following AVERAGING_TIME_MINUTES - instead of treating every raw sample as an
independent characteristic-map observation. build_stable_observations() is the
batch (Phase 1 simulator) variant; SteadyPeriodDetector is the incremental,
pandas-free counterpart for live (Phase 2) use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from . import config

REQUIRED_COLUMNS = ("outdoor_temp", "compressor_frequency", "charge_pump_speed", "cop")


def _stability_group_ids(df: pd.DataFrame) -> pd.Series:
    """Assign a group id per row; a new group starts on a time gap or an out-of-tolerance jump."""
    speed_tolerance = config.CHARGE_PUMP_SPEED_STABILITY_TOLERANCE_PERCENT
    frequency_tolerance = config.COMPRESSOR_FREQUENCY_STABILITY_TOLERANCE_HZ
    max_gap = pd.Timedelta(minutes=config.MAX_SAMPLE_GAP_MINUTES)

    time_gap = df.index.to_series().diff()
    speed_jump = df["charge_pump_speed"].diff().abs()
    frequency_jump = df["compressor_frequency"].diff().abs()

    starts_new_group = (
        time_gap.isna()
        | (time_gap > max_gap)
        | (speed_jump > speed_tolerance)
        | (frequency_jump > frequency_tolerance)
    )
    return starts_new_group.cumsum()


def build_stable_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse df into one averaged observation per steady period long enough to settle+average.

    Requires a sorted DatetimeIndex and REQUIRED_COLUMNS (as returned by
    influx_loader.load_data()). Periods shorter than SETTLING_TIME_MINUTES +
    AVERAGING_TIME_MINUTES are dropped entirely (no partial observation).
    """
    columns = list(REQUIRED_COLUMNS)
    if df.empty:
        return df[columns]

    settling = pd.Timedelta(minutes=config.SETTLING_TIME_MINUTES)
    min_duration = settling + pd.Timedelta(minutes=config.AVERAGING_TIME_MINUTES)

    group_ids = _stability_group_ids(df)
    records = []
    for _, group in df.groupby(group_ids):
        duration = group.index[-1] - group.index[0]
        if duration < min_duration:
            continue
        averaging_window = group[group.index >= group.index[0] + settling]
        if averaging_window.empty:
            continue
        record = averaging_window[columns].mean()
        record.name = averaging_window.index[-1]
        records.append(record)

    if not records:
        return df.iloc[0:0][columns]

    result = pd.DataFrame(records)
    result.index.name = df.index.name
    return result.sort_index()


@dataclass
class Observation:
    """One completed, settled+averaged observation ready for CharacteristicMap.update()."""

    timestamp: datetime
    outdoor_temp: float
    compressor_frequency: float
    charge_pump_speed: float
    cop: float


class SteadyPeriodDetector:
    """Incremental (live) counterpart to build_stable_observations() for one data stream.

    Feed samples one at a time via observe(). While a steady period is settling,
    it returns None; once settled, it returns a fresh averaged Observation every
    AVERAGING_TIME_MINUTES for as long as the period stays stable (repeated
    confirmations of the same operating point), without needing to re-settle.
    """

    def __init__(
        self,
        settling_minutes: float | None = None,
        averaging_minutes: float | None = None,
        max_sample_gap_minutes: float | None = None,
        speed_tolerance_percent: float | None = None,
        frequency_tolerance_hz: float | None = None,
    ) -> None:
        self._settling = timedelta(minutes=settling_minutes or config.SETTLING_TIME_MINUTES)
        self._averaging = timedelta(minutes=averaging_minutes or config.AVERAGING_TIME_MINUTES)
        self._max_gap = timedelta(minutes=max_sample_gap_minutes or config.MAX_SAMPLE_GAP_MINUTES)
        self._speed_tolerance = (
            speed_tolerance_percent or config.CHARGE_PUMP_SPEED_STABILITY_TOLERANCE_PERCENT
        )
        self._frequency_tolerance = (
            frequency_tolerance_hz or config.COMPRESSOR_FREQUENCY_STABILITY_TOLERANCE_HZ
        )
        self._last_sample: tuple[datetime, float, float] | None = None  # timestamp, speed, frequency
        self._window: list[tuple[datetime, float, float, float, float]] = []
        self._window_start: datetime | None = None
        self._settled = False

    def reset(self) -> None:
        """Discard all in-progress state, e.g. after an external control/error-status change."""
        self._last_sample = None
        self._window = []
        self._window_start = None
        self._settled = False

    def observe(
        self,
        timestamp: datetime,
        outdoor_temp: float,
        compressor_frequency: float,
        charge_pump_speed: float,
        cop: float,
    ) -> Observation | None:
        """Feed one sample; returns a completed Observation once settled+averaged, else None."""
        if self._last_sample is not None:
            last_timestamp, last_speed, last_frequency = self._last_sample
            broke_stability = (
                (timestamp - last_timestamp) > self._max_gap
                or abs(charge_pump_speed - last_speed) > self._speed_tolerance
                or abs(compressor_frequency - last_frequency) > self._frequency_tolerance
            )
            if broke_stability:
                self.reset()

        self._last_sample = (timestamp, charge_pump_speed, compressor_frequency)

        if self._window_start is None:
            self._window_start = timestamp

        if not self._settled:
            if (timestamp - self._window_start) < self._settling:
                return None
            # Settling just completed; start the averaging window fresh from here.
            self._settled = True
            self._window_start = timestamp
            self._window = []

        self._window.append((timestamp, outdoor_temp, compressor_frequency, charge_pump_speed, cop))

        if (timestamp - self._window_start) < self._averaging:
            return None

        count = len(self._window)
        observation = Observation(
            timestamp=self._window[-1][0],
            outdoor_temp=sum(sample[1] for sample in self._window) / count,
            compressor_frequency=sum(sample[2] for sample in self._window) / count,
            charge_pump_speed=sum(sample[3] for sample in self._window) / count,
            cop=sum(sample[4] for sample in self._window) / count,
        )
        self._window_start = timestamp
        self._window = []
        return observation
