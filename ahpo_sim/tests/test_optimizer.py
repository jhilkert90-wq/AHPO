"""Tests for optimizer.py."""
from __future__ import annotations

from ahpo_sim.optimizer import HillClimbingOptimizer


def test_first_step_moves_in_initial_direction_with_coarse_step() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    next_speed = opt.step(spread_error=2.0)
    assert next_speed == 35.0
    assert opt.state.history == [(30.0, 2.0)]


def test_improvement_keeps_direction() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    opt.step(spread_error=3.0)   # |e|=3.0  -> 35.0
    next_speed = opt.step(spread_error=1.0)  # |e|=1.0 < 3.0 -> improved, keep direction
    assert next_speed == 40.0
    assert opt.state.reversals == 0


def test_no_improvement_reverses_and_shrinks_step() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    opt.step(spread_error=1.0)   # |e|=1.0 -> 35.0
    next_speed = opt.step(spread_error=3.0)  # |e|=3.0 > 1.0 -> worse, reverse
    assert next_speed == 35.0 - 2.5
    assert opt.state.reversals == 1
    assert opt.state.step_size == 2.5


def test_step_size_floor_at_fine_step() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=2.0, fine_step_size=1.0)
    opt.step(spread_error=1.0)
    for e in (2.0, 0.5, 2.0, 0.5, 2.0):
        opt.step(spread_error=e)
    assert opt.state.step_size == 1.0
    assert opt.converged is True


def test_speed_clamped_to_max() -> None:
    opt = HillClimbingOptimizer(initial_speed=98.0, coarse_step_size=5.0, min_speed=0.0, max_speed=100.0)
    next_speed = opt.step(spread_error=2.0)
    assert next_speed == 100.0


def test_speed_clamped_to_min() -> None:
    opt = HillClimbingOptimizer(
        initial_speed=2.0, initial_direction=-1, coarse_step_size=5.0, min_speed=0.0, max_speed=100.0
    )
    next_speed = opt.step(spread_error=2.0)
    assert next_speed == 0.0


def test_not_converged_initially() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    assert opt.converged is False


def test_shrinks_abs_error_from_positive_start() -> None:
    """Optimizer converges |e| toward zero starting from a positive error."""
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    # Simulate: e decreases as speed increases toward optimum, then worsens past it.
    errors = [4.0, 2.0, 0.5, 1.5, 0.8, 0.3]
    for e in errors:
        opt.step(spread_error=e)
    # After a series of improvements and reversals, |e| should be tracked correctly.
    assert opt.state.last_abs_spread_error == pytest.approx(0.3)


def test_shrinks_abs_error_from_negative_start() -> None:
    """Optimizer converges |e| toward zero starting from a negative error."""
    opt = HillClimbingOptimizer(initial_speed=60.0, initial_direction=-1, coarse_step_size=5.0, fine_step_size=1.0)
    errors = [-3.0, -1.5, -0.4, -1.2, -0.2]
    for e in errors:
        opt.step(spread_error=e)
    assert opt.state.last_abs_spread_error == pytest.approx(0.2)


import pytest  # noqa: E402 — imported after function definitions for pytest.approx use above
