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
    """One grid cell: gliding estimate of the optimal charge-pump speed and its spread error."""

    outdoor_temp_bin: float
    compressor_freq_bin: float
    optimal_charge_pump_speed: float | None = None
    best_abs_spread_error: float = math.inf  # smallest |e| seen; lower is better
    best_spread_error_speed: float | None = None  # pump speed that produced best_abs_spread_error
    n_measurements: int = 0
    spread_error_mean: float = 0.0
    spread_error_m2: float = 0.0  # Welford accumulator for spread-error variance
    spread_error_std: float = 0.0  # kept up-to-date after each record()
    spread_error_weight_sum: float = 0.0  # cumulative weight backing optimal_charge_pump_speed
    cop_mean_logged: float = 0.0  # unweighted arithmetic mean of COP — informational only
    n_cop_measurements: int = 0  # number of observations that carried a valid COP value
    last_updated: datetime | None = None
    source: str = "passive"  # "passive" (Phase A) or "active" (Phase B)
    confidence_score: float = 0.0

    def record(
        self,
        charge_pump_speed: float,
        spread_error: float,
        cop: float = math.nan,
        timestamp: datetime | None = None,
        source: str = "passive",
    ) -> None:
        """Blend in one new (pump speed, spread_error) observation. Never overwrites outright."""
        self.n_measurements += 1

        # Welford's online mean/variance update for spread-error.
        delta = spread_error - self.spread_error_mean
        self.spread_error_mean += delta / self.n_measurements
        delta2 = spread_error - self.spread_error_mean
        self.spread_error_m2 += delta * delta2
        if self.n_measurements >= 2:
            self.spread_error_std = math.sqrt(self.spread_error_m2 / (self.n_measurements - 1))
        else:
            self.spread_error_std = 0.0

        # Gliding, precision-weighted update of the optimal speed: observations with a
        # smaller |e| (closer to zero error) pull the estimate more strongly.
        weight_value = 1.0 / (abs(spread_error) + 1e-3)
        self.spread_error_weight_sum += weight_value
        if self.optimal_charge_pump_speed is None:
            self.optimal_charge_pump_speed = charge_pump_speed
        else:
            weight = weight_value / self.spread_error_weight_sum
            self.optimal_charge_pump_speed += weight * (
                charge_pump_speed - self.optimal_charge_pump_speed
            )
        if abs(spread_error) < self.best_abs_spread_error:
            self.best_abs_spread_error = abs(spread_error)
            self.best_spread_error_speed = charge_pump_speed

        # Informational COP running mean (unweighted, no influence on optimization).
        # Uses its own counter so NaN observations don't bias the average.
        if not (cop is None or (isinstance(cop, float) and math.isnan(cop))):
            self.n_cop_measurements += 1
            cop_delta = cop - self.cop_mean_logged
            self.cop_mean_logged += cop_delta / self.n_cop_measurements

        self.last_updated = timestamp
        self.source = source

    def to_dict(self) -> dict[str, float | int | str | None]:
        """Plain-dict representation (JSON-serializable, suitable for HA storage)."""
        return {
            "outdoor_temp_bin": self.outdoor_temp_bin,
            "compressor_freq_bin": self.compressor_freq_bin,
            "optimal_charge_pump_speed": self.optimal_charge_pump_speed,
            "best_abs_spread_error": self.best_abs_spread_error if math.isfinite(self.best_abs_spread_error) else None,
            "best_spread_error_speed": self.best_spread_error_speed,
            "n_measurements": self.n_measurements,
            "spread_error_mean": self.spread_error_mean,
            "spread_error_std": self.spread_error_std,
            "spread_error_weight_sum": self.spread_error_weight_sum,
            "cop_mean_logged": self.cop_mean_logged,
            "n_cop_measurements": self.n_cop_measurements,
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
        spread_error: float,
        cop: float = math.nan,
        timestamp: datetime | None = None,
        source: str = "passive",
    ) -> CharacteristicMapCell:
        """Record one observation (Phase A or Phase B) into its map cell."""
        if any(_is_missing(v) for v in (outdoor_temp, compressor_frequency, charge_pump_speed, spread_error)):
            raise ValueError("CharacteristicMap.update() received a missing input; filter rows first.")
        cell = self.get_cell(outdoor_temp, compressor_frequency, create=True)
        cell.record(charge_pump_speed, spread_error, cop=cop, timestamp=timestamp, source=source)
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
        """Reconstruct cells from to_dict() records; spread_error_m2 recovered from spread_error_std."""
        if replace:
            self._cells = {}
        for record in records:
            n = int(record["n_measurements"])
            spread_error_std = float(record["spread_error_std"]) if record.get("spread_error_std") is not None else 0.0
            spread_error_m2 = (spread_error_std**2) * (n - 1) if n >= 2 else 0.0
            spread_error_mean = float(record.get("spread_error_mean") or 0.0)
            spread_error_weight_sum = record.get("spread_error_weight_sum")
            spread_error_weight_sum = (
                float(spread_error_weight_sum) if spread_error_weight_sum is not None
                else 1.0 / (abs(spread_error_mean) + 1e-3) * n
            )
            best_abs_raw = record.get("best_abs_spread_error")
            best_abs_spread_error = float(best_abs_raw) if best_abs_raw is not None else math.inf
            best_spread_error_speed_raw = record.get("best_spread_error_speed")
            last_updated_raw = record.get("last_updated")
            last_updated = datetime.fromisoformat(last_updated_raw) if last_updated_raw else None
            optimal_speed = record.get("optimal_charge_pump_speed")
            cell = CharacteristicMapCell(
                outdoor_temp_bin=float(record["outdoor_temp_bin"]),
                compressor_freq_bin=float(record["compressor_freq_bin"]),
                optimal_charge_pump_speed=float(optimal_speed) if optimal_speed is not None else None,
                best_abs_spread_error=best_abs_spread_error,
                best_spread_error_speed=float(best_spread_error_speed_raw) if best_spread_error_speed_raw is not None else None,
                n_measurements=n,
                spread_error_mean=spread_error_mean,
                spread_error_m2=spread_error_m2,
                spread_error_std=spread_error_std,
                spread_error_weight_sum=spread_error_weight_sum,
                cop_mean_logged=float(record.get("cop_mean_logged") or 0.0),
                n_cop_measurements=int(record.get("n_cop_measurements") or 0),
                last_updated=last_updated,
                source=str(record["source"]),
                confidence_score=float(record["confidence_score"]),
            )
            self._cells[(cell.outdoor_temp_bin, cell.compressor_freq_bin)] = cell
