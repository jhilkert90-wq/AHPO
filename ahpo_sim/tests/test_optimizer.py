"""Tests for optimizer.py — ProportionalSpreadController."""
from __future__ import annotations

import pytest

from ahpo_sim.optimizer import ProportionalSpreadController


def _ctrl(initial_speed: float = 50.0, kp: float = 2.0, deadband_k: float = 0.3, max_step: float = 5.0) -> ProportionalSpreadController:
    return ProportionalSpreadController(
        initial_speed=initial_speed,
        kp=kp,
        deadband_k=deadband_k,
        max_step_percent=max_step,
        min_speed=0.0,
        max_speed=100.0,
    )


def test_positive_error_increases_speed() -> None:
    """Positive spread_error must increase speed on the very first call — no exploration needed."""
    ctrl = _ctrl(initial_speed=50.0)
    next_speed = ctrl.step(spread_error=1.0)
    assert next_speed > 50.0


def test_negative_error_decreases_speed() -> None:
    """Negative spread_error must decrease speed on the very first call."""
    ctrl = _ctrl(initial_speed=50.0)
    next_speed = ctrl.step(spread_error=-1.0)
    assert next_speed < 50.0


def test_deadband_holds_speed_and_sets_flag() -> None:
    """|spread_error| <= deadband_k leaves speed unchanged and sets in_deadband=True."""
    ctrl = _ctrl(deadband_k=0.3)
    next_speed = ctrl.step(spread_error=0.2)
    assert next_speed == pytest.approx(50.0)
    assert ctrl.state.in_deadband is True
    assert ctrl.state.consecutive_in_deadband_ticks == 1


def test_exact_deadband_boundary_holds() -> None:
    ctrl = _ctrl(deadband_k=0.3)
    next_speed = ctrl.step(spread_error=0.3)
    assert next_speed == pytest.approx(50.0)
    assert ctrl.state.in_deadband is True


def test_just_outside_deadband_steps() -> None:
    ctrl = _ctrl(deadband_k=0.3, kp=2.0)
    next_speed = ctrl.step(spread_error=0.31)
    assert next_speed > 50.0
    assert ctrl.state.in_deadband is False


def test_raw_step_clamped_to_max_step_percent() -> None:
    """A large spread_error is clamped to max_step_percent."""
    ctrl = _ctrl(kp=2.0, max_step=5.0)
    next_speed = ctrl.step(spread_error=10.0)  # raw_step = 20% > 5%
    assert next_speed == pytest.approx(55.0)


def test_max_speed_bound() -> None:
    ctrl = _ctrl(initial_speed=98.0, kp=2.0, max_step=5.0)
    next_speed = ctrl.step(spread_error=5.0)
    assert next_speed == pytest.approx(100.0)


def test_min_speed_bound() -> None:
    ctrl = _ctrl(initial_speed=2.0, kp=2.0, max_step=5.0)
    next_speed = ctrl.step(spread_error=-5.0)
    assert next_speed == pytest.approx(0.0)


def test_history_recorded() -> None:
    ctrl = _ctrl(initial_speed=50.0)
    ctrl.step(spread_error=1.0)
    ctrl.step(spread_error=0.5)
    assert ctrl.state.history[0] == (50.0, 1.0)
    assert len(ctrl.state.history) == 2


def test_converged_property_reflects_deadband() -> None:
    ctrl = _ctrl()
    assert ctrl.converged is False
    ctrl.step(spread_error=0.1)  # inside deadband
    assert ctrl.converged is True


def test_last_step_applied_zero_in_deadband() -> None:
    ctrl = _ctrl()
    ctrl.step(spread_error=0.1)
    assert ctrl.state.last_step_applied == pytest.approx(0.0)


def test_last_step_applied_correct_outside_deadband() -> None:
    ctrl = _ctrl(initial_speed=50.0, kp=2.0, max_step=5.0)
    ctrl.step(spread_error=1.0)  # raw = 2%, clamped = 2%, speed 52
    assert ctrl.state.last_step_applied == pytest.approx(2.0)


def test_monotonic_convergence_with_small_kp() -> None:
    """Repeated calls with shrinking spread_error converge toward zero without oscillating past it."""
    ctrl = _ctrl(initial_speed=40.0, kp=0.5, deadband_k=0.05, max_step=5.0)
    errors = [4.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.04]
    speeds = []
    for e in errors:
        speed = ctrl.step(e)
        speeds.append(speed)
    # Speed should monotonically increase (all errors positive -> always step up)
    for i in range(len(speeds) - 1):
        assert speeds[i] <= speeds[i + 1] or ctrl.state.in_deadband


def test_consecutive_deadband_ticks_resets_on_exit() -> None:
    ctrl = _ctrl(deadband_k=0.3)
    ctrl.step(spread_error=0.1)
    ctrl.step(spread_error=0.1)
    assert ctrl.state.consecutive_in_deadband_ticks == 2
    ctrl.step(spread_error=1.0)  # outside deadband
    assert ctrl.state.consecutive_in_deadband_ticks == 0
    assert ctrl.state.in_deadband is False
