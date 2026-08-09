"""Tests for characteristic_map.py."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from ahpo_sim.characteristic_map import CharacteristicMap


def test_cell_key_binning_positive_and_negative() -> None:
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    assert cm.cell_key(5.9, 41.0) == (4.0, 40.0)
    assert cm.cell_key(-1.2, 40.0) == (-2.0, 40.0)


def test_lookup_returns_none_for_unknown_cell() -> None:
    cm = CharacteristicMap()
    assert cm.lookup(5.0, 40.0) is None


def test_update_creates_cell_and_records_values() -> None:
    cm = CharacteristicMap()
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=0.5)
    assert cell.n_measurements == 1
    assert cell.optimal_charge_pump_speed == 30.0
    assert cell.best_abs_spread_error == pytest.approx(0.5)
    assert cm.lookup(5.0, 40.0) is cell


def test_update_raises_on_missing_values() -> None:
    cm = CharacteristicMap()
    with pytest.raises(ValueError):
        cm.update(math.nan, 40.0, charge_pump_speed=30.0, spread_error=0.5)


def test_record_zero_spread_error_uses_max_weight() -> None:
    # e=0 → weight = 1/(0+1e-3) = 1000 (highest possible), should dominate.
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=5.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=60.0, spread_error=0.0)
    assert cell.n_measurements == 2
    # The zero-error observation should pull optimal speed strongly toward 60.
    assert cell.optimal_charge_pump_speed > 30.0


def test_spread_error_std_with_single_measurement_is_zero() -> None:
    cm = CharacteristicMap()
    cell = cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0)
    assert cell.spread_error_std == 0.0


def test_gliding_update_moves_towards_lower_abs_error_speed() -> None:
    cm = CharacteristicMap()
    # First observation: large error (low weight)
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=5.0)
    # Second observation: small error at speed 40 (high weight)
    cell = cm.update(5.0, 40.0, charge_pump_speed=40.0, spread_error=0.1)
    assert cell.optimal_charge_pump_speed > 30.0
    assert cell.best_abs_spread_error == pytest.approx(0.1)
    assert cell.best_spread_error_speed == pytest.approx(40.0)


def test_cop_mean_logged_is_informational_only() -> None:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0, cop=4.0)
    cell = cm.update(5.0, 40.0, charge_pump_speed=32.0, spread_error=0.5, cop=5.0)
    # cop_mean_logged should be the arithmetic mean of the COP values
    assert cell.cop_mean_logged == pytest.approx(4.5)


def test_to_dataframe_shape() -> None:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0)
    cm.update(9.0, 44.0, charge_pump_speed=35.0, spread_error=0.5)
    df = cm.to_dataframe()
    assert len(df) == 2
    assert "confidence_score" in df.columns


def test_to_dict_from_dict_round_trip() -> None:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0,
              cop=4.0, timestamp=pd.Timestamp("2026-01-01"))
    records = cm.to_dict()

    restored = CharacteristicMap()
    restored.from_dict(records)

    original_cell = cm.lookup(5.0, 40.0)
    restored_cell = restored.lookup(5.0, 40.0)
    assert restored_cell is not None
    assert restored_cell.optimal_charge_pump_speed == original_cell.optimal_charge_pump_speed
    assert restored_cell.n_measurements == original_cell.n_measurements
    assert restored_cell.cop_mean_logged == pytest.approx(original_cell.cop_mean_logged)


def test_export_csv_round_trip(tmp_path) -> None:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0)
    path = tmp_path / "characteristic_map.csv"
    cm.export_csv(path)
    loaded = pd.read_csv(path)
    assert len(loaded) == 1
    assert loaded.loc[0, "optimal_charge_pump_speed"] == 30.0


def test_export_json_round_trip(tmp_path) -> None:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=0.8)
    path = tmp_path / "characteristic_map.json"
    cm.export_json(path)
    loaded = pd.read_json(path)
    assert len(loaded) == 1
    assert loaded.loc[0, "best_abs_spread_error"] == pytest.approx(0.8)


def _build_varied_map() -> CharacteristicMap:
    cm = CharacteristicMap()
    cm.update(5.0, 40.0, charge_pump_speed=30.0, spread_error=1.0, timestamp=pd.Timestamp("2026-01-01"))
    cm.update(5.0, 40.0, charge_pump_speed=32.0, spread_error=0.5, timestamp=pd.Timestamp("2026-01-02"))
    cm.update(9.0, 44.0, charge_pump_speed=50.0, spread_error=2.0, timestamp=pd.Timestamp("2026-01-03"))
    return cm


def test_import_csv_reconstructs_cell_fields(tmp_path) -> None:
    original = _build_varied_map()
    path = tmp_path / "characteristic_map.csv"
    original.export_csv(path)

    imported = CharacteristicMap()
    imported.import_csv(path)

    original_cell = original.lookup(5.0, 40.0)
    imported_cell = imported.lookup(5.0, 40.0)
    assert imported_cell is not None
    assert imported_cell.n_measurements == original_cell.n_measurements
    assert imported_cell.optimal_charge_pump_speed == pytest.approx(original_cell.optimal_charge_pump_speed)
    assert imported_cell.spread_error_std == pytest.approx(original_cell.spread_error_std)
    assert imported_cell.spread_error_weight_sum == pytest.approx(original_cell.spread_error_weight_sum)


def test_import_csv_round_trip_preserves_phase_decisions(tmp_path) -> None:
    from ahpo_sim.phase_manager import PhaseManager

    original = _build_varied_map()
    path = tmp_path / "characteristic_map.csv"

    original_pm = PhaseManager(original, confidence_threshold=0.5, min_samples=2, max_spread_error_std=1.0)
    for cell in original.all_cells():
        original_pm.update_confidence(cell)
    original.export_csv(path)

    imported = CharacteristicMap()
    imported.import_csv(path)
    imported_pm = PhaseManager(imported, confidence_threshold=0.5, min_samples=2, max_spread_error_std=1.0)

    for key in [(5.0, 40.0), (9.0, 44.0)]:
        original_cell = original.lookup(*key)
        imported_cell = imported.lookup(*key)
        assert imported_pm.get_phase(imported_cell) == original_pm.get_phase(original_cell)
        assert imported_cell.confidence_score == pytest.approx(original_cell.confidence_score)
