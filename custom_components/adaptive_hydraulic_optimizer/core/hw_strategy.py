"""Separate control strategy for domestic hot water (HW/DHW) charging.

Target: keep the primary flow temperature at ``target + offset`` (default +1 K) for as
long as the compressor runs.  Pump speed rises when the flow is too hot (more flow
removes more heat) and falls when it is too cold.  No learning, no COP, no map updates.
"""
from __future__ import annotations

import math

DHW_MODE = "dhw"
DEFAULT_DHW_STATE = "hw"
DHW_STATE_ALIASES = frozenset({"hw", "dhw", "hotwater", "hot_water", "warmwasser", "brauchwasser"})


def is_dhw_state(raw_state: str | None, configured_state: str | None = None) -> bool:
    """True if the raw operating-mode state denotes hot-water operation."""
    if raw_state is None:
        return False
    state = raw_state.strip().lower()
    if configured_state and state == configured_state.strip().lower():
        return True
    return state in DHW_STATE_ALIASES


def clamp_standby_speed(speed: float, min_speed: float) -> float:
    """Limit the standby speed to [min_speed, 100]."""
    return min(100.0, max(min_speed, speed))


class DhwController:
    """Proportional controller with deadband and step limit for the HW charge pump."""

    def __init__(
        self,
        offset_k: float = 1.0,
        kp: float = 5.0,
        deadband_k: float = 0.2,
        max_step_percent: float = 5.0,
        min_speed: float = 15.0,
        max_speed: float = 100.0,
    ) -> None:
        self.offset_k = offset_k
        self.kp = kp
        self.deadband_k = deadband_k
        self.max_step_percent = max_step_percent
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.last_error_k: float | None = None

    def reset(self) -> None:
        self.last_error_k = None

    def update(self, flow_temp: float, target_temp: float, current_speed: float) -> float:
        """Return the new pump speed (unchanged inside the deadband)."""
        if any(math.isnan(v) for v in (flow_temp, target_temp, current_speed)):
            return current_speed
        error = flow_temp - (target_temp + self.offset_k)
        self.last_error_k = error
        if abs(error) <= self.deadband_k:
            return current_speed
        step = max(-self.max_step_percent, min(self.max_step_percent, self.kp * error))
        return min(self.max_speed, max(self.min_speed, current_speed + step))
