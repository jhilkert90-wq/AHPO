"""Tests for interpolation.py."""
from __future__ import annotations

from ahpo_sim.characteristic_map import CharacteristicMap
from ahpo_sim.interpolation import interpolate_optimal_speed, lookup_nearest


def test_lookup_nearest_matches_characteristic_map_lookup() -> None:
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    cell = cm.update(5.0, 41.0, charge_pump_speed=30.0, cop=4.0)
    assert lookup_nearest(cm, 5.0, 41.0) is cell


def test_interpolate_optimal_speed_returns_none_when_no_data() -> None:
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    assert interpolate_optimal_speed(cm, 5.0, 41.0) is None


def test_interpolate_optimal_speed_blends_all_four_corners() -> None:
    # Edge case: exact midpoint between 4 populated cells -> plain average.
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    cm.update(4.0, 40.0, charge_pump_speed=20.0, cop=4.0)
    cm.update(4.0, 42.0, charge_pump_speed=30.0, cop=4.0)
    cm.update(6.0, 40.0, charge_pump_speed=40.0, cop=4.0)
    cm.update(6.0, 42.0, charge_pump_speed=50.0, cop=4.0)

    result = interpolate_optimal_speed(cm, 5.0, 41.0)
    assert result == 35.0


def test_interpolate_optimal_speed_exact_on_grid_point() -> None:
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    cm.update(4.0, 40.0, charge_pump_speed=20.0, cop=4.0)

    result = interpolate_optimal_speed(cm, 4.0, 40.0)
    assert result == 20.0


def test_interpolate_optimal_speed_falls_back_with_partial_neighbors() -> None:
    # Edge case: only 1 of 4 neighbors has data -> normalized weight still resolves it.
    cm = CharacteristicMap(outdoor_temp_step=2.0, compressor_freq_step=2.0)
    cm.update(4.0, 40.0, charge_pump_speed=20.0, cop=4.0)

    result = interpolate_optimal_speed(cm, 5.0, 41.0)
    assert result == 20.0
