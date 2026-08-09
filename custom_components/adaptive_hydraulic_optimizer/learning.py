"""One learning cycle: feed a settled observation into the characteristic map, update
confidence/phase, and drive the optimizer for active cells.

No Home Assistant imports here - this stays testable/simulatable independent of HA.
"""
from __future__ import annotations

from dataclasses import dataclass

from .core.characteristic_map import CharacteristicMap, CharacteristicMapCell
from .core.optimizer import ProportionalSpreadController
from .core.phase_manager import Phase, PhaseManager
from .core.timing import Observation


@dataclass
class LearningResult:
    """Outcome of processing one settled Observation."""

    cell: CharacteristicMapCell
    phase: Phase
    proposed_charge_pump_speed: float | None  # only set when phase is ACTIVE
    operating_mode: str  # "cool" or "heat"
    # Controller state snapshot (only populated when phase is ACTIVE)
    controller_step_applied: float = 0.0
    controller_in_deadband: bool = False
    controller_consecutive_deadband_ticks: int = 0
    improving: bool = False  # True when |spread_error| decreased since previous observation
    is_first_observation: bool = False  # True on the very first tick for this cell


class LearningEngine:
    """Ties the characteristic map, phase manager and per-cell controllers together."""

    def __init__(
        self,
        cool_map: CharacteristicMap,
        heat_map: CharacteristicMap,
        phase_manager: PhaseManager,
        min_charge_pump_speed: float = 0.0,
        spread_controller_kp: float | None = None,
        spread_controller_deadband_k: float | None = None,
        spread_controller_max_step_percent: float | None = None,
    ) -> None:
        self._cool_map = cool_map
        self._heat_map = heat_map
        self._phase_manager = phase_manager
        self._min_charge_pump_speed = min_charge_pump_speed
        self._spread_controller_kp = spread_controller_kp
        self._spread_controller_deadband_k = spread_controller_deadband_k
        self._spread_controller_max_step_percent = spread_controller_max_step_percent
        self._controllers: dict[tuple[str, float, float], ProportionalSpreadController] = {}

    @property
    def min_charge_pump_speed(self) -> float:
        return self._min_charge_pump_speed

    @min_charge_pump_speed.setter
    def min_charge_pump_speed(self, value: float) -> None:
        self._min_charge_pump_speed = value

    @property
    def spread_controller_kp(self) -> float:
        from .core.optimizer import SPREAD_CONTROLLER_KP
        return self._spread_controller_kp if self._spread_controller_kp is not None else SPREAD_CONTROLLER_KP

    @spread_controller_kp.setter
    def spread_controller_kp(self, value: float) -> None:
        self._spread_controller_kp = value
        for ctrl in self._controllers.values():
            ctrl.kp = value

    @property
    def spread_controller_deadband_k(self) -> float:
        from .core.optimizer import SPREAD_CONTROLLER_DEADBAND_K
        return self._spread_controller_deadband_k if self._spread_controller_deadband_k is not None else SPREAD_CONTROLLER_DEADBAND_K

    @spread_controller_deadband_k.setter
    def spread_controller_deadband_k(self, value: float) -> None:
        self._spread_controller_deadband_k = value
        for ctrl in self._controllers.values():
            ctrl.deadband_k = value

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
            observation.spread_error,
            cop=observation.cop,
            timestamp=observation.timestamp,
            source="passive",
        )
        self._phase_manager.update_confidence(cell, reference_time=observation.timestamp)
        phase = self._phase_manager.get_effective_phase(
            cell, error_status=error_status, reference_time=observation.timestamp
        )

        proposed_speed: float | None = None
        controller_step_applied: float = 0.0
        controller_in_deadband: bool = False
        controller_consecutive_deadband_ticks: int = 0
        improving: bool = False
        is_first_observation: bool = False
        if phase is Phase.ACTIVE:
            key = (
                operating_mode,
                *characteristic_map.cell_key(
                    observation.outdoor_temp, observation.compressor_frequency
                ),
            )
            controller = self._controllers.setdefault(
                key, ProportionalSpreadController(
                    initial_speed=recorded_speed,
                    kp=self._spread_controller_kp,
                    deadband_k=self._spread_controller_deadband_k,
                    max_step_percent=self._spread_controller_max_step_percent,
                    min_speed=self._min_charge_pump_speed,
                )
            )
            prev_abs = controller.state.last_spread_error
            improving = (
                prev_abs is not None and abs(observation.spread_error) < abs(prev_abs)
            )
            is_first_observation = prev_abs is None
            proposed_speed = controller.step(observation.spread_error)
            controller_step_applied = controller.state.last_step_applied
            controller_in_deadband = controller.state.in_deadband
            controller_consecutive_deadband_ticks = controller.state.consecutive_in_deadband_ticks
            cell.source = "active"
            # Pin the stored optimal speed to the empirically best-error speed so it always
            # reflects the speed that achieved the smallest |e|, not the weighted mean
            # of all explored speeds.
            if cell.best_spread_error_speed is not None:
                cell.optimal_charge_pump_speed = cell.best_spread_error_speed

        return LearningResult(
            cell=cell,
            phase=phase,
            proposed_charge_pump_speed=proposed_speed,
            operating_mode=operating_mode,
            controller_step_applied=controller_step_applied,
            controller_in_deadband=controller_in_deadband,
            controller_consecutive_deadband_ticks=controller_consecutive_deadband_ticks,
            improving=improving,
            is_first_observation=is_first_observation,
        )
