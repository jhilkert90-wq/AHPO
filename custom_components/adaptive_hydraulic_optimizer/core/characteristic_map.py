"""Characteristic map: outdoor-temp x compressor-frequency grid of learned pump-speed/COP cells.

Pure Python, no pandas dependency (safe for an async Home Assistant integration).
CSV/JSON file export/import live in ahpo_sim (Phase 1 simulator) only; this module's
to_dict()/from_dict() are the serialization primitives used by storage.py instead.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

MAP_OUTDOOR_TEMP_STEP_C: float = 2.0
MAP_COMPRESSOR_FREQ_STEP_HZ: float = 2.0


def _is_missing(value: float | None) -> bool:
    """True for None or NaN, without requiring pandas."""
    return value is None or (isinstance(value, float) and math.isnan(value))


@dataclass
class CharacteristicMapCell:
    """One grid cell: gliding estimate of the optimal charge-pump speed and its COP."""

    outdoor_temp_bin: float
    compressor_freq_bin: float
    optimal_charge_pump_speed: float | None = None
    best_cop: float = -math.inf
    best_cop_speed: float | None = None  # pump speed that produced best_cop
    n_measurements: int = 0
    cop_mean: float = 0.0
    cop_m2: float = 0.0  # Welford accumulator for COP variance
    cop_weight_sum: float = 0.0  # cumulative COP weight backing optimal_charge_pump_speed
    last_updated: datetime | None = None
    source: str = "passive"  # "passive" (Phase A) or "active" (Phase B)
    confidence_score: float = 0.0

    @property
    def cop_std(self) -> float:
        if self.n_measurements < 2:
            return 0.0
        return math.sqrt(self.cop_m2 / (self.n_measurements - 1))

    def record(
        self,
        charge_pump_speed: float,
        cop: float,
        timestamp: datetime | None = None,
        source: str = "passive",
    ) -> None:
        """Blend in one new (pump speed, COP) observation. Never overwrites outright."""
        self.n_measurements += 1

        # Welford's online mean/variance update for COP spread.
        delta = cop - self.cop_mean
        self.cop_mean += delta / self.n_measurements
        delta2 = cop - self.cop_mean
        self.cop_m2 += delta * delta2

        # Gliding, COP-weighted update of the optimal speed: observations with a
        # higher COP magnitude pull the estimate more strongly, and the step size
        # shrinks automatically as more (weight-carrying) observations accumulate.
        # abs(cop) is used as the weight so cooling (negative COP) is handled
        # correctly — a higher (less negative) COP still wins via the best_cop
        # comparison below.
        weight_value = abs(cop) if cop != 0 else 1e-6
        self.cop_weight_sum += weight_value
        if self.optimal_charge_pump_speed is None:
            self.optimal_charge_pump_speed = charge_pump_speed
        else:
            weight = weight_value / self.cop_weight_sum
            self.optimal_charge_pump_speed += weight * (
                charge_pump_speed - self.optimal_charge_pump_speed
            )
        if cop > self.best_cop:
            self.best_cop = cop
            self.best_cop_speed = charge_pump_speed

        self.last_updated = timestamp
        self.source = source

    def to_dict(self) -> dict[str, float | int | str | None]:
        """Plain-dict representation (JSON-serializable, suitable for HA storage)."""
        return {
            "outdoor_temp_bin": self.outdoor_temp_bin,
            "compressor_freq_bin": self.compressor_freq_bin,
            "optimal_charge_pump_speed": self.optimal_charge_pump_speed,
            "best_cop": self.best_cop if math.isfinite(self.best_cop) else None,
            "best_cop_speed": self.best_cop_speed,
            "n_measurements": self.n_measurements,
            "cop_mean": self.cop_mean,
            "cop_std": self.cop_std,
            "cop_weight_sum": self.cop_weight_sum,
            "confidence_score": self.confidence_score,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "source": self.source,
        }


class CharacteristicMap:
    """Grid of CharacteristicMapCell instances, indexed by binned (outdoor_temp, compressor_frequency)."""

    def __init__(
        self,
        outdoor_temp_step: float | None = None,
        compressor_freq_step: float | None = None,
    ) -> None:
        self._outdoor_temp_step = outdoor_temp_step or MAP_OUTDOOR_TEMP_STEP_C
        self._compressor_freq_step = compressor_freq_step or MAP_COMPRESSOR_FREQ_STEP_HZ
        self._cells: dict[tuple[float, float], CharacteristicMapCell] = {}

    @property
    def outdoor_temp_step(self) -> float:
        return self._outdoor_temp_step

    @property
    def compressor_freq_step(self) -> float:
        return self._compressor_freq_step

    @staticmethod
    def _bin(value: float, step: float) -> float:
        return round(math.floor(value / step) * step, 6)

    def cell_key(self, outdoor_temp: float, compressor_frequency: float) -> tuple[float, float]:
        return (
            self._bin(outdoor_temp, self._outdoor_temp_step),
            self._bin(compressor_frequency, self._compressor_freq_step),
        )

    def get_cell(
        self, outdoor_temp: float, compressor_frequency: float, create: bool = False
    ) -> CharacteristicMapCell | None:
        key = self.cell_key(outdoor_temp, compressor_frequency)
        cell = self._cells.get(key)
        if cell is None and create:
            cell = CharacteristicMapCell(outdoor_temp_bin=key[0], compressor_freq_bin=key[1])
            self._cells[key] = cell
        return cell

    def lookup(self, outdoor_temp: float, compressor_frequency: float) -> CharacteristicMapCell | None:
        """Read-only lookup; returns None if the cell has no data yet."""
        return self.get_cell(outdoor_temp, compressor_frequency, create=False)

    def update(
        self,
        outdoor_temp: float,
        compressor_frequency: float,
        charge_pump_speed: float,
        cop: float,
        timestamp: datetime | None = None,
        source: str = "passive",
    ) -> CharacteristicMapCell:
        """Record one observation (Phase A or Phase B) into its map cell."""
        if any(_is_missing(v) for v in (outdoor_temp, compressor_frequency, charge_pump_speed, cop)):
            raise ValueError("CharacteristicMap.update() received a missing input; filter rows first.")
        cell = self.get_cell(outdoor_temp, compressor_frequency, create=True)
        cell.record(charge_pump_speed, cop, timestamp=timestamp, source=source)
        return cell

    def all_cells(self) -> list[CharacteristicMapCell]:
        return list(self._cells.values())

    def clear(self) -> None:
        """Discard all learned cells in place (existing references keep working)."""
        self._cells = {}

    def to_dict(self) -> list[dict[str, float | int | str | None]]:
        """Plain-dict records of all cells (JSON-serializable, suitable for HA storage)."""
        return [cell.to_dict() for cell in self._cells.values()]

    def from_dict(self, records: list[dict], replace: bool = True) -> None:
        """Reconstruct cells from to_dict() records; cop_m2 is recovered exactly from cop_std."""
        if replace:
            self._cells = {}
        for record in records:
            n = int(record["n_measurements"])
            cop_std = float(record["cop_std"]) if record.get("cop_std") is not None else 0.0
            cop_m2 = (cop_std**2) * (n - 1) if n >= 2 else 0.0
            cop_mean = float(record["cop_mean"]) if record.get("cop_mean") is not None else 0.0
            cop_weight_sum = record.get("cop_weight_sum")
            cop_weight_sum = (
                float(cop_weight_sum) if cop_weight_sum is not None else abs(cop_mean) * n
            )  # approx fallback for records without this field
            last_updated_raw = record.get("last_updated")
            last_updated = datetime.fromisoformat(last_updated_raw) if last_updated_raw else None
            optimal_speed = record.get("optimal_charge_pump_speed")
            best_cop_speed_raw = record.get("best_cop_speed")
            cell = CharacteristicMapCell(
                outdoor_temp_bin=float(record["outdoor_temp_bin"]),
                compressor_freq_bin=float(record["compressor_freq_bin"]),
                optimal_charge_pump_speed=float(optimal_speed) if optimal_speed is not None else None,
                best_cop=float(record["best_cop"]) if record.get("best_cop") is not None else -math.inf,
                best_cop_speed=float(best_cop_speed_raw) if best_cop_speed_raw is not None else None,
                n_measurements=n,
                cop_mean=cop_mean,
                cop_m2=cop_m2,
                cop_weight_sum=cop_weight_sum,
                last_updated=last_updated,
                source=str(record["source"]),
                confidence_score=float(record["confidence_score"]),
            )
            self._cells[(cell.outdoor_temp_bin, cell.compressor_freq_bin)] = cell
