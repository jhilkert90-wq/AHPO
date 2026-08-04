"""Characteristic-map lookup helpers: nearest-cell (default) and bilinear interpolation.

Pure Python, no pandas dependency - safe to vendor into a Home Assistant integration.
"""
from __future__ import annotations

from .characteristic_map import CharacteristicMap, CharacteristicMapCell


def lookup_nearest(
    characteristic_map: CharacteristicMap, outdoor_temp: float, compressor_frequency: float
) -> CharacteristicMapCell | None:
    """Nearest-cell characteristic-map lookup (same grid cell the observation would fall into)."""
    return characteristic_map.lookup(outdoor_temp, compressor_frequency)


def interpolate_optimal_speed(
    characteristic_map: CharacteristicMap, outdoor_temp: float, compressor_frequency: float
) -> float | None:
    """Bilinear interpolation of optimal_charge_pump_speed between the 4 neighboring cells.

    Falls back to the nearest cell's value if fewer than 4 neighbors have data yet
    (e.g. at the edges of the observed range, or early in learning).
    """
    outdoor_step = characteristic_map.outdoor_temp_step
    frequency_step = characteristic_map.compressor_freq_step

    low_temp, low_freq = characteristic_map.cell_key(outdoor_temp, compressor_frequency)
    high_temp = low_temp + outdoor_step
    high_freq = low_freq + frequency_step

    temp_weight = (outdoor_temp - low_temp) / outdoor_step
    freq_weight = (compressor_frequency - low_freq) / frequency_step

    corners = {
        (low_temp, low_freq): (1 - temp_weight) * (1 - freq_weight),
        (low_temp, high_freq): (1 - temp_weight) * freq_weight,
        (high_temp, low_freq): temp_weight * (1 - freq_weight),
        (high_temp, high_freq): temp_weight * freq_weight,
    }

    weighted_sum = 0.0
    weight_total = 0.0
    for (temp_bin, freq_bin), weight in corners.items():
        cell = characteristic_map.get_cell(temp_bin, freq_bin, create=False)
        if cell is None or cell.optimal_charge_pump_speed is None or weight <= 0:
            continue
        weighted_sum += weight * cell.optimal_charge_pump_speed
        weight_total += weight

    if weight_total <= 0:
        nearest = lookup_nearest(characteristic_map, outdoor_temp, compressor_frequency)
        return nearest.optimal_charge_pump_speed if nearest is not None else None

    return weighted_sum / weight_total
