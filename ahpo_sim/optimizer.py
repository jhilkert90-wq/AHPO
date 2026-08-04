"""Hill-climbing optimizer with adaptive step size (Phase B only)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class HillClimbingState:
    current_speed: float
    direction: int = 1  # +1 (increase speed) or -1 (decrease speed)
    step_size: float = 0.0
    last_cop: float | None = None
    history: list[tuple[float, float]] = field(default_factory=list)  # (speed, cop)
    reversals: int = 0


class HillClimbingOptimizer:
    """Classic hill climbing: keep direction while COP improves, else reverse and shrink step.

    Step size starts coarse (unknown territory) and shrinks towards a fine floor
    once the optimum's vicinity has been found (i.e. after direction reversals).
    """

    def __init__(
        self,
        initial_speed: float,
        initial_direction: int = 1,
        coarse_step_size: float | None = None,
        fine_step_size: float | None = None,
        min_speed: float = 0.0,
        max_speed: float = 100.0,
    ) -> None:
        self._fine_step_size = fine_step_size or config.CHARGE_PUMP_STEP_PERCENT
        self._coarse_step_size = coarse_step_size or config.CHARGE_PUMP_STEP_PERCENT_COARSE
        self._min_speed = min_speed
        self._max_speed = max_speed
        self.state = HillClimbingState(
            current_speed=initial_speed,
            direction=1 if initial_direction >= 0 else -1,
            step_size=self._coarse_step_size,
        )

    @property
    def converged(self) -> bool:
        """True once the step size has shrunk to the fine floor (near the optimum)."""
        return self.state.step_size <= self._fine_step_size

    def step(self, cop: float) -> float:
        """Record the COP measured at the current speed and propose the next speed."""
        state = self.state
        improved = state.last_cop is None or cop > state.last_cop
        if state.last_cop is not None and not improved:
            state.direction *= -1
            state.step_size = max(state.step_size / 2, self._fine_step_size)
            state.reversals += 1

        state.history.append((state.current_speed, cop))
        state.last_cop = cop

        next_speed = state.current_speed + state.direction * state.step_size
        next_speed = min(max(next_speed, self._min_speed), self._max_speed)
        state.current_speed = next_speed
        return next_speed

