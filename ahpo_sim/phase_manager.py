"""Phase-A (passive/shadow) vs. Phase-B (active) logic per characteristic-map cell.

Confidence formula:
    confidence = min(1, n_measurements / CONFIDENCE_MIN_SAMPLES)
                 * 1 / (1 + spread_error_std / CONFIDENCE_MAX_SPREAD_ERROR_STD)
                 * 0.5 ** (age_days / CONFIDENCE_AGE_HALFLIFE_DAYS)
A cell moves from Phase A to Phase B once confidence >= CONFIDENCE_THRESHOLD. The age
factor only applies when a reference_time is passed in; it defaults to no decay.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from . import config
from .characteristic_map import CharacteristicMap, CharacteristicMapCell


class Phase(str, Enum):
    PASSIVE = "passiv_lernend"
    ACTIVE = "aktiv_optimierend"


class PhaseManager:
    """Computes per-cell confidence and derives the effective Phase A/B state."""

    def __init__(
        self,
        characteristic_map: CharacteristicMap,
        confidence_threshold: float | None = None,
        min_samples: int | None = None,
        max_spread_error_std: float | None = None,
        global_override: Phase | None = None,
        age_halflife_days: float | None = None,
    ) -> None:
        self._characteristic_map = characteristic_map
        self._confidence_threshold = confidence_threshold or config.CONFIDENCE_THRESHOLD
        self._min_samples = min_samples or config.CONFIDENCE_MIN_SAMPLES
        self._max_spread_error_std = max_spread_error_std or config.CONFIDENCE_MAX_SPREAD_ERROR_STD
        self._global_override = global_override
        self._age_halflife_days = age_halflife_days or config.CONFIDENCE_AGE_HALFLIFE_DAYS

    def calculate_confidence(
        self, cell: CharacteristicMapCell, reference_time: datetime | None = None
    ) -> float:
        """Confidence in [0, 1] from sample count, spread-error std and data age (if reference_time given)."""
        if cell.n_measurements <= 0:
            return 0.0
        sample_component = min(1.0, cell.n_measurements / self._min_samples)
        stability_component = 1.0 / (1.0 + cell.spread_error_std / self._max_spread_error_std)
        age_factor = 1.0
        if reference_time is not None and cell.last_updated is not None:
            age_days = max(0.0, (reference_time - cell.last_updated).total_seconds() / 86400.0)
            age_factor = 0.5 ** (age_days / self._age_halflife_days)
        return max(0.0, min(1.0, sample_component * stability_component * age_factor))

    def update_confidence(
        self, cell: CharacteristicMapCell, reference_time: datetime | None = None
    ) -> float:
        cell.confidence_score = self.calculate_confidence(cell, reference_time=reference_time)
        return cell.confidence_score

    def set_global_override(self, phase: Phase | None) -> None:
        """Force all cells into one phase (e.g. an "activate active phase" service), or None to clear."""
        self._global_override = phase

    def get_phase(self, cell: CharacteristicMapCell, reference_time: datetime | None = None) -> Phase:
        if self._global_override is not None:
            return self._global_override
        if cell.n_measurements <= 0:
            return Phase.PASSIVE
        confidence = (
            self.calculate_confidence(cell, reference_time=reference_time)
            if reference_time is not None
            else cell.confidence_score
        )
        return Phase.ACTIVE if confidence >= self._confidence_threshold else Phase.PASSIVE

    def get_effective_phase(
        self,
        cell: CharacteristicMapCell,
        error_status: bool | None = None,
        reference_time: datetime | None = None,
    ) -> Phase:
        """Like get_phase(), but falls back to Phase A on sensor/error faults (safety fallback)."""
        if error_status:
            return Phase.PASSIVE
        return self.get_phase(cell, reference_time=reference_time)

    def active_cell_fraction(self, reference_time: datetime | None = None) -> float:
        """Share of known map cells currently released for Phase B."""
        cells = self._characteristic_map.all_cells()
        if not cells:
            return 0.0
        active = sum(
            1 for cell in cells if self.get_phase(cell, reference_time=reference_time) == Phase.ACTIVE
        )
        return active / len(cells)

