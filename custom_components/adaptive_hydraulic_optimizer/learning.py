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
    operating_mode: str  # "cool" or "heat"
    # Hill-climber state snapshot (only populated when phase is ACTIVE)
    hill_climb_direction: int = 0
    hill_climb_step_size: float = 0.0
    hill_climb_reversals: int = 0
    hill_climb_improved: bool = False


class LearningEngine:
    """Ties the characteristic map, phase manager and per-cell optimizers together."""

    def __init__(
        self,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
        phase_manager: PhaseManager,
        min_charge_pump_speed: float = 0.0,
        charge_pump_step_percent: float | None = None,
        charge_pump_step_percent_coarse: float | None = None,
    ) -> None:
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._phase_manager = phase_manager
        self._min_charge_pump_speed = min_charge_pump_speed
        self._charge_pump_step_percent = charge_pump_step_percent
        self._charge_pump_step_percent_coarse = charge_pump_step_percent_coarse
        self._optimizers: dict[tuple[str, float, float], HillClimbingOptimizer] = {}

    @property
    def min_charge_pump_speed(self) -> float:
        return self._min_charge_pump_speed

    @min_charge_pump_speed.setter
    def min_charge_pump_speed(self, value: float) -> None:
        self._min_charge_pump_speed = value

    def _active_map(self, operating_mode: str) -> CharacteristicMap:
        """Return the characteristic map for the given operating mode."""
        return self._cool_map if operating_mode == "cool" else self._heat_map

    def process(
        self,
        observation: Observation,
        error_status: bool = False,
        operating_mode: str = "heat",
    ) -> LearningResult:
        """Record one settled observation and decide the next action."""
        characteristic_map = self._active_map(operating_mode)

        # Hard-clamp the recorded charge pump speed to the configured minimum so
        # observations taken at a speed that is too low for reliable flow metering
        # are not stored as-is — they learn the minimum speed instead.
        recorded_speed = max(observation.charge_pump_speed, self._min_charge_pump_speed)

        cell = characteristic_map.update(
            observation.outdoor_temp,
            observation.compressor_frequency,
            recorded_speed,
            observation.cop,
            timestamp=observation.timestamp,
            source="passive",
        )
        self._phase_manager.update_confidence(cell, reference_time=observation.timestamp)
        phase = self._phase_manager.get_effective_phase(
            cell, error_status=error_status, reference_time=observation.timestamp
        )

        proposed_speed: float | None = None
        hill_climb_direction: int = 0
        hill_climb_step_size: float = 0.0
        hill_climb_reversals: int = 0
        hill_climb_improved: bool = False
        if phase is Phase.ACTIVE:
            key = (
                operating_mode,
                *characteristic_map.cell_key(
                    observation.outdoor_temp, observation.compressor_frequency
                ),
            )
            optimizer = self._optimizers.setdefault(
                key, HillClimbingOptimizer(
                    initial_speed=recorded_speed,
                    min_speed=self._min_charge_pump_speed,
                    fine_step_size=self._charge_pump_step_percent,
                    coarse_step_size=self._charge_pump_step_percent_coarse,
                )
            )
            # Capture the state *before* the step so we can report whether COP improved.
            prev_cop = optimizer.state.last_cop
            hill_climb_improved = prev_cop is None or observation.cop > prev_cop
            proposed_speed = optimizer.step(observation.cop)
            hill_climb_direction = optimizer.state.direction
            hill_climb_step_size = optimizer.state.step_size
            hill_climb_reversals = optimizer.state.reversals
            cell.source = "active"
            # Pin the stored optimal speed to the empirically best speed so it always
            # reflects the speed that achieved the highest COP, not the weighted mean
            # of all explored speeds (which is pulled toward sub-optimal exploration points).
            if cell.best_cop_speed is not None:
                cell.optimal_charge_pump_speed = cell.best_cop_speed

        return LearningResult(
            cell=cell,
            phase=phase,
            proposed_charge_pump_speed=proposed_speed,
            operating_mode=operating_mode,
            hill_climb_direction=hill_climb_direction,
            hill_climb_step_size=hill_climb_step_size,
            hill_climb_reversals=hill_climb_reversals,
            hill_climb_improved=hill_climb_improved,
        )
