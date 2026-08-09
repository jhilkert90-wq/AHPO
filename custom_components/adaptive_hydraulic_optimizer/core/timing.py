"""Incremental (live) steady-period detection matching the spec's settling/averaging model.

After a pump-speed/frequency change (or once stability is detected), wait
SETTLING_TIME_MINUTES for the system to settle, then average COP over the
following AVERAGING_TIME_MINUTES. Pure Python, no pandas dependency. The batch
equivalent (for the offline Phase 1 simulator) lives in ahpo_sim.timing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SETTLING_TIME_MINUTES: float = 3.0
AVERAGING_TIME_MINUTES: float = 5.0
MAX_SAMPLE_GAP_MINUTES: float = 10.0
CHARGE_PUMP_SPEED_STABILITY_TOLERANCE_PERCENT: float = 2.0
COMPRESSOR_FREQUENCY_STABILITY_TOLERANCE_HZ: float = 2.0


@dataclass
class Observation:
    """One completed, settled+averaged observation ready for CharacteristicMap.update()."""

    timestamp: datetime
    outdoor_temp: float
    compressor_frequency: float
    charge_pump_speed: float
    cop: float
    spread_error: float = 0.0


class SteadyPeriodDetector:
    """Feed samples one at a time via observe(). While a steady period is settling,
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
        self._settling = timedelta(minutes=settling_minutes or SETTLING_TIME_MINUTES)
        self._averaging = timedelta(minutes=averaging_minutes or AVERAGING_TIME_MINUTES)
        self._max_gap = timedelta(minutes=max_sample_gap_minutes or MAX_SAMPLE_GAP_MINUTES)
        self._speed_tolerance = speed_tolerance_percent or CHARGE_PUMP_SPEED_STABILITY_TOLERANCE_PERCENT
        self._frequency_tolerance = (
            frequency_tolerance_hz or COMPRESSOR_FREQUENCY_STABILITY_TOLERANCE_HZ
        )
        self._last_sample: tuple[datetime, float, float] | None = None  # timestamp, speed, frequency
        self._window: list[tuple[datetime, float, float, float, float, float]] = []
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
        spread_error: float = 0.0,
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

        self._window.append((timestamp, outdoor_temp, compressor_frequency, charge_pump_speed, cop, spread_error))

        if (timestamp - self._window_start) < self._averaging:
            return None

        count = len(self._window)
        observation = Observation(
            timestamp=self._window[-1][0],
            outdoor_temp=sum(sample[1] for sample in self._window) / count,
            compressor_frequency=sum(sample[2] for sample in self._window) / count,
            charge_pump_speed=sum(sample[3] for sample in self._window) / count,
            cop=sum(sample[4] for sample in self._window) / count,
            spread_error=sum(sample[5] for sample in self._window) / count,
        )
        self._window_start = timestamp
        self._window = []
        return observation
