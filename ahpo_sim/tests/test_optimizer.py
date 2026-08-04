"""Tests for optimizer.py."""
from __future__ import annotations

from ahpo_sim.optimizer import HillClimbingOptimizer


def test_first_step_moves_in_initial_direction_with_coarse_step() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    next_speed = opt.step(cop=4.0)
    assert next_speed == 35.0
    assert opt.state.history == [(30.0, 4.0)]


def test_improvement_keeps_direction() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    opt.step(cop=4.0)  # -> 35.0
    next_speed = opt.step(cop=5.0)  # improved -> keep direction
    assert next_speed == 40.0
    assert opt.state.reversals == 0


def test_no_improvement_reverses_and_shrinks_step() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    opt.step(cop=4.0)  # -> 35.0
    next_speed = opt.step(cop=3.0)  # worse -> reverse direction, shrink step
    assert next_speed == 35.0 - 2.5
    assert opt.state.reversals == 1
    assert opt.state.step_size == 2.5


def test_step_size_floor_at_fine_step() -> None:
    # Edge case: repeated reversals must not shrink the step below the fine floor.
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=2.0, fine_step_size=1.0)
    opt.step(cop=4.0)
    for cop_value in (3.0, 3.5, 3.0, 3.5, 3.0):
        opt.step(cop=cop_value)
    assert opt.state.step_size == 1.0
    assert opt.converged is True


def test_speed_clamped_to_max() -> None:
    opt = HillClimbingOptimizer(initial_speed=98.0, coarse_step_size=5.0, min_speed=0.0, max_speed=100.0)
    next_speed = opt.step(cop=4.0)
    assert next_speed == 100.0


def test_speed_clamped_to_min() -> None:
    opt = HillClimbingOptimizer(
        initial_speed=2.0, initial_direction=-1, coarse_step_size=5.0, min_speed=0.0, max_speed=100.0
    )
    next_speed = opt.step(cop=4.0)
    assert next_speed == 0.0


def test_not_converged_initially() -> None:
    opt = HillClimbingOptimizer(initial_speed=30.0, coarse_step_size=5.0, fine_step_size=1.0)
    assert opt.converged is False
