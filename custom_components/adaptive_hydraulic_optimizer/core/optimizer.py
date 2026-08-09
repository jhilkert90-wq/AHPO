"""Proportional spread-error controller for Phase B pump-speed regulation."""
from __future__ import annotations

from dataclasses import dataclass, field

SPREAD_CONTROLLER_KP: float = 2.0  # TODO: tune against ahpo_sim results
SPREAD_CONTROLLER_DEADBAND_K: float = 0.3
SPREAD_CONTROLLER_MAX_STEP_PERCENT: float = 5.0


@dataclass
class ProportionalControllerState:
    current_speed: float
    last_spread_error: float | None = None
    last_step_applied: float = 0.0
    in_deadband: bool = False
    consecutive_in_deadband_ticks: int = 0
    history: list[tuple[float, float]] = field(default_factory=list)  # (speed, spread_error)


class ProportionalSpreadController:
    """P-only controller: sign of spread_error directly determines the required direction.

    spread_error = ΔT_primary − ΔT_secondary.
    e > 0 → pump too slow → increase speed.
    e < 0 → pump too fast → decrease speed.
    Inside the deadband the speed is held unchanged to avoid micro-hunting.
    """

    def __init__(
        self,
        initial_speed: float,
        kp: float | None = None,
        deadband_k: float | None = None,
        max_step_percent: float | None = None,
        min_speed: float = 0.0,
        max_speed: float = 100.0,
    ) -> None:
        self._kp = kp if kp is not None else SPREAD_CONTROLLER_KP
        self._deadband_k = deadband_k if deadband_k is not None else SPREAD_CONTROLLER_DEADBAND_K
        self._max_step_percent = max_step_percent if max_step_percent is not None else SPREAD_CONTROLLER_MAX_STEP_PERCENT
        self._min_speed = min_speed
        self._max_speed = max_speed
        self.state = ProportionalControllerState(current_speed=initial_speed)

    @property
    def kp(self) -> float:
        return self._kp

    @kp.setter
    def kp(self, value: float) -> None:
        self._kp = value

    @property
    def deadband_k(self) -> float:
        return self._deadband_k

    @deadband_k.setter
    def deadband_k(self, value: float) -> None:
        self._deadband_k = value

    @property
    def converged(self) -> bool:
        """True once the controller is inside the deadband (speed is held)."""
        return self.state.in_deadband

    def step(self, spread_error: float) -> float:
        """Record spread_error at the current speed and return the next commanded speed."""
        state = self.state
        state.history.append((state.current_speed, spread_error))

        if abs(spread_error) <= self._deadband_k:
            state.in_deadband = True
            state.consecutive_in_deadband_ticks += 1
            state.last_step_applied = 0.0
            state.last_spread_error = spread_error
            return state.current_speed

        state.in_deadband = False
        state.consecutive_in_deadband_ticks = 0

        raw_step = self._kp * spread_error
        clamped_step = max(-self._max_step_percent, min(self._max_step_percent, raw_step))
        next_speed = state.current_speed + clamped_step
        next_speed = max(self._min_speed, min(self._max_speed, next_speed))

        state.last_step_applied = next_speed - state.current_speed
        state.last_spread_error = spread_error
        state.current_speed = next_speed
        return next_speed
