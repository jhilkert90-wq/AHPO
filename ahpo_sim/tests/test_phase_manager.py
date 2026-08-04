"""Tests for phase_manager.py."""
from __future__ import annotations

import pandas as pd

from ahpo_sim.characteristic_map import CharacteristicMap
from ahpo_sim.phase_manager import Phase, PhaseManager


def test_zero_measurements_is_passive() -> None:
    # Edge case: a cell with no data yet must never be Phase B.
    cm = CharacteristicMap()
    pm = PhaseManager(cm)
    cell = cm.get_cell(5.0, 40.0, create=True)
    assert pm.calculate_confidence(cell) == 0.0
    assert pm.get_phase(cell) == Phase.PASSIVE


def test_confidence_below_threshold_stays_passive() -> None:
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.7, min_samples=5, max_cop_std=1.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0)
    pm.update_confidence(cell)
    assert pm.get_phase(cell) == Phase.PASSIVE


def test_confidence_at_or_above_threshold_becomes_active() -> None:
    # Edge case: boundary at exactly the configured threshold.
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.5, min_samples=2, max_cop_std=1.0)
    for _ in range(5):
        cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0)
    pm.update_confidence(cell)
    assert cell.confidence_score >= 0.5
    assert pm.get_phase(cell) == Phase.ACTIVE


def test_global_override_forces_phase_regardless_of_confidence() -> None:
    cm = CharacteristicMap()
    pm = PhaseManager(cm, global_override=Phase.ACTIVE)
    cell = cm.get_cell(5.0, 40.0, create=True)  # no measurements at all
    assert pm.get_phase(cell) == Phase.ACTIVE

    pm.set_global_override(Phase.PASSIVE)
    assert pm.get_phase(cell) == Phase.PASSIVE


def test_error_status_forces_passive_fallback() -> None:
    # Edge case: safety fallback must win even if confidence is high.
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.5, min_samples=2, max_cop_std=1.0)
    for _ in range(5):
        cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0)
    pm.update_confidence(cell)
    assert pm.get_effective_phase(cell, error_status=True) == Phase.PASSIVE


def test_active_cell_fraction_with_no_cells_is_zero() -> None:
    # Edge case: an empty characteristic map must not raise a ZeroDivisionError.
    cm = CharacteristicMap()
    pm = PhaseManager(cm)
    assert pm.active_cell_fraction() == 0.0


def test_active_cell_fraction_mixed() -> None:
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.5, min_samples=5, max_cop_std=1.0)
    for _ in range(5):
        active_cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0)
    passive_cell = cm.update(9.0, 44.0, charge_pump_speed=30.0, cop=4.0)
    pm.update_confidence(active_cell)
    pm.update_confidence(passive_cell)
    assert pm.active_cell_fraction() == 0.5


def test_confidence_no_reference_time_no_decay() -> None:
    # Backward compatibility: without a reference_time, age must not affect confidence.
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.5, min_samples=2, max_cop_std=1.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0, timestamp=pd.Timestamp("2026-01-01"))
    assert pm.calculate_confidence(cell) == pm.calculate_confidence(cell, reference_time=None)


def test_confidence_age_decay_reduces_score() -> None:
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.5, min_samples=2, max_cop_std=1.0, age_halflife_days=30.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0, timestamp=pd.Timestamp("2026-01-01"))
    fresh = pm.calculate_confidence(cell, reference_time=pd.Timestamp("2026-01-01"))
    stale = pm.calculate_confidence(cell, reference_time=pd.Timestamp("2026-02-15"))
    assert stale < fresh


def test_get_phase_drops_to_passive_after_long_staleness() -> None:
    # Edge case: a cell that was confidently active can decay back to passive over time.
    cm = CharacteristicMap()
    pm = PhaseManager(cm, confidence_threshold=0.7, min_samples=1, max_cop_std=100.0, age_halflife_days=30.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, cop=4.0, timestamp=pd.Timestamp("2026-01-01"))
    pm.update_confidence(cell, reference_time=pd.Timestamp("2026-01-01"))
    assert pm.get_phase(cell) == Phase.ACTIVE

    one_halflife_later = pd.Timestamp("2026-01-01") + pd.Timedelta(days=30)
    assert pm.get_phase(cell, reference_time=one_halflife_later) == Phase.PASSIVE

