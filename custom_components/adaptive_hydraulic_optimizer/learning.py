"""One learning cycle: feed a settled observation into the characteristic map, update
confidence/phase, and drive the optimizer for active cells.

No Home Assistant imports here - this stays testable/simulatable independent of HA.
"""
from __future__ import annotations

from dataclasses import dataclass

from .core.characteristic_map import CharacteristicMap, CharacteristicMapCell
from .core.optimizer import HillClimbingOptimizer
from .core.phase_manager import Phase, PhaseManager
from .core.timing import Observation


@dataclass
class LearningResult:
    """Outcome of processing one settled Observation."""

    cell: CharacteristicMapCell
    phase: Phase
    proposed_charge_pump_speed: float | None  # only set when phase is ACTIVE


class LearningEngine:
    """Ties the characteristic map, phase manager and per-cell optimizers together."""

    def __init__(self, characteristic_map: CharacteristicMap, phase_manager: PhaseManager) -> None:
        self._characteristic_map = characteristic_map
        self._phase_manager = phase_manager
        self._optimizers: dict[tuple[float, float], HillClimbingOptimizer] = {}

    def process(self, observation: Observation, error_status: bool = False) -> LearningResult:
        """Record one settled observation and decide the next action."""
        cell = self._characteristic_map.update(
            observation.outdoor_temp,
            observation.compressor_frequency,
            observation.charge_pump_speed,
            observation.cop,
            timestamp=observation.timestamp,
            source="passive",
        )
        self._phase_manager.update_confidence(cell, reference_time=observation.timestamp)
        phase = self._phase_manager.get_effective_phase(
            cell, error_status=error_status, reference_time=observation.timestamp
        )

        proposed_speed: float | None = None
        if phase is Phase.ACTIVE:
            key = self._characteristic_map.cell_key(
                observation.outdoor_temp, observation.compressor_frequency
            )
            optimizer = self._optimizers.setdefault(
                key, HillClimbingOptimizer(initial_speed=observation.charge_pump_speed)
            )
            proposed_speed = optimizer.step(observation.cop)
            cell.source = "active"

        return LearningResult(cell=cell, phase=phase, proposed_charge_pump_speed=proposed_speed)
