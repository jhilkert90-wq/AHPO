"""Orchestrates the time-index-based simulation run over historical data."""
from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from . import cop as cop_module
from . import influx_loader
from . import timing
from .characteristic_map import CharacteristicMap, characteristic_map_heatmap
from .optimizer import HillClimbingOptimizer
from .phase_manager import Phase, PhaseManager

__all__ = ["SimulationResult", "run_simulation", "add_cop_column", "add_spread_error_column", "characteristic_map_heatmap"]

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("outdoor_temp", "compressor_frequency", "charge_pump_speed", "cop", "spread_error")


def add_cop_column(df: pd.DataFrame, default_mode: str | None = None) -> pd.DataFrame:
    """Vectorized COP/thermal-power computation, added as new columns (batch/simulator only).

    COP is calculated only for rows whose resolved operating mode is 'heat' or 'cool'.
    Any row with other mode values gets NaN COP and is skipped by downstream processing.
    """
    result = df.copy()

    resolved_default_mode = cop_module.resolve_mode(default_mode)
    if "operating_mode" in result.columns:
        modes = result["operating_mode"].map(cop_module.resolve_mode)
        if resolved_default_mode is not None:
            modes = modes.fillna(resolved_default_mode)
    else:
        modes = pd.Series(resolved_default_mode, index=result.index)

    valid_modes = modes.isin((cop_module.HEATING, cop_module.COOLING))
    delta_t = (result["primary_flow_temp"] - result["primary_return_temp"]).abs()
    delta_t = delta_t.where(valid_modes, math.nan)

    flow_rate_l_h = result["primary_flow_rate"] * 60.0
    thermal_power_w = config.HEAT_CAPACITY_FACTOR_WH_PER_L_K * flow_rate_l_h * delta_t

    electrical_power_w = result["electrical_power_total"]
    cop = thermal_power_w / electrical_power_w
    cop = cop.where(electrical_power_w > 0, math.nan)
    cop = cop.where(valid_modes, math.nan)
    cop = cop.clip(upper=config.COP_MAX_PLAUSIBLE)

    result["delta_t"] = delta_t
    result["thermal_power_w"] = thermal_power_w
    result["cop"] = cop
    return result


def add_spread_error_column(df: pd.DataFrame, default_mode: str | None = None) -> pd.DataFrame:
    """Compute and attach a signed spread_error column (primary ΔT − secondary ΔT).

    Rows without resolvable mode or missing secondary temperature columns get NaN.
    The COP column must already exist (call add_cop_column first).
    """
    result = df.copy()

    resolved_default_mode = cop_module.resolve_mode(default_mode)
    if "operating_mode" in result.columns:
        modes = result["operating_mode"].map(cop_module.resolve_mode)
        if resolved_default_mode is not None:
            modes = modes.fillna(resolved_default_mode)
    else:
        modes = pd.Series(resolved_default_mode, index=result.index)

    valid_modes = modes.isin((cop_module.HEATING, cop_module.COOLING))

    primary_dt = (result["primary_flow_temp"] - result["primary_return_temp"]).abs()
    primary_dt = primary_dt.where(valid_modes, math.nan)

    if "secondary_flow_temp" in result.columns and "secondary_return_temp" in result.columns:
        secondary_dt = (result["secondary_flow_temp"] - result["secondary_return_temp"]).abs()
        secondary_dt = secondary_dt.where(valid_modes, math.nan)
    else:
        secondary_dt = pd.Series(math.nan, index=result.index)

    result["spread_error"] = primary_dt - secondary_dt
    return result


@dataclass
class SimulationResult:
    """Aggregated outputs of one historical simulation run."""

    characteristic_map: CharacteristicMap
    phase_manager: PhaseManager
    cop_series: pd.Series
    spread_error_series: pd.Series
    active_cell_fraction_over_time: pd.Series
    optimizer_traces: dict[tuple[float, float], list[tuple[float, float]]] = field(
        default_factory=dict
    )


def run_simulation(
    df: pd.DataFrame | None = None,
    default_mode: str | None = None,
    use_stable_periods: bool = True,
    initial_map: CharacteristicMap | None = None,
) -> SimulationResult:
    """Replay historical data row-by-row to build the characteristic map and phase state.

    Phase A (passive) ingestion happens for every valid row (or, by default, every
    settled steady period - see timing.build_stable_observations). Once a cell's
    confidence crosses the configured threshold, subsequent observations for
    that cell also drive a HillClimbingOptimizer trace (simulated Phase B).

    Note: with strict mode gating, data without resolvable operating_mode values
    ('heat'/'cool', or configured numeric codes) is ignored.
    """
    if df is None:
        df = influx_loader.load_data()
    df = add_cop_column(df, default_mode=default_mode)
    df = add_spread_error_column(df, default_mode=default_mode)

    # Drop rows where COP or spread_error is unavailable.  cop must be > 0 (physical);
    # spread_error may be any sign — only NaN means the row is unusable.
    valid = df.dropna(subset=["outdoor_temp", "compressor_frequency", "charge_pump_speed", "cop", "spread_error"])
    valid = valid[valid["cop"] > 0]

    outdoor_temp_min, outdoor_temp_max = config.OUTDOOR_TEMP_PLAUSIBLE_RANGE_C
    speed_min, speed_max = config.CHARGE_PUMP_SPEED_PLAUSIBLE_RANGE_PERCENT
    implausible = (
        ~valid["outdoor_temp"].between(outdoor_temp_min, outdoor_temp_max)
        | ~valid["charge_pump_speed"].between(speed_min, speed_max)
    )
    if implausible.any():
        logger.warning("Dropping %d row(s) with implausible sensor values", implausible.sum())
        valid = valid[~implausible]

    below_min_frequency = valid["compressor_frequency"] < config.MIN_COMPRESSOR_FREQUENCY_HZ
    if below_min_frequency.any():
        logger.info(
            "Dropping %d row(s) with compressor_frequency below MIN_COMPRESSOR_FREQUENCY_HZ (%.1f Hz)",
            below_min_frequency.sum(),
            config.MIN_COMPRESSOR_FREQUENCY_HZ,
        )
        valid = valid[~below_min_frequency]

    if use_stable_periods:
        raw_row_count = len(valid)
        valid = timing.build_stable_observations(valid)
        logger.info(
            "Settling/averaging model: %d raw row(s) collapsed into %d stable observation(s)",
            raw_row_count,
            len(valid),
        )

    characteristic_map = initial_map if initial_map is not None else CharacteristicMap()
    phase_manager = PhaseManager(characteristic_map)
    optimizers: dict[tuple[float, float], HillClimbingOptimizer] = {}
    active_fraction_index: list[pd.Timestamp] = []
    active_fraction_values: list[float] = []

    logger.info("Starting simulation over %d valid rows", len(valid))

    for timestamp, row in valid.iterrows():
        outdoor_temp = row["outdoor_temp"]
        compressor_frequency = row["compressor_frequency"]
        charge_pump_speed = row["charge_pump_speed"]
        cop_value = row["cop"]
        spread_error = row["spread_error"]

        cell = characteristic_map.update(
            outdoor_temp,
            compressor_frequency,
            charge_pump_speed,
            spread_error,
            cop=cop_value,
            timestamp=timestamp,
            source="passive",
        )
        phase_manager.update_confidence(cell, reference_time=timestamp)

        if phase_manager.get_phase(cell) is Phase.ACTIVE:
            key = characteristic_map.cell_key(outdoor_temp, compressor_frequency)
            optimizer = optimizers.setdefault(
                key, HillClimbingOptimizer(initial_speed=charge_pump_speed)
            )
            optimizer.step(spread_error)
            cell.source = "active"

        active_fraction_index.append(timestamp)
        active_fraction_values.append(phase_manager.active_cell_fraction(reference_time=timestamp))

    active_cell_fraction_over_time = pd.Series(
        active_fraction_values, index=active_fraction_index, name="active_cell_fraction"
    )

    logger.info(
        "Simulation finished: %d characteristic map cells, %d active optimizer traces",
        len(characteristic_map.all_cells()),
        len(optimizers),
    )

    optimizer_traces = {key: optimizer.state.history for key, optimizer in optimizers.items()}

    return SimulationResult(
        characteristic_map=characteristic_map,
        phase_manager=phase_manager,
        cop_series=valid["cop"],
        spread_error_series=valid["spread_error"],
        active_cell_fraction_over_time=active_cell_fraction_over_time,
        optimizer_traces=optimizer_traces,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AHPO Phase 1 historical-data simulation.")
    parser.add_argument("--csv-path", type=str, default=None, help="Override the historical CSV file (default: config.CSV_PATH).")
    parser.add_argument(
        "--plot-output",
        type=str,
        default="ahpo_sim/output/simulation_summary.png",
        help="Where to save the summary plot (PNG).",
    )
    parser.add_argument("--no-plot", action="store_true", help="Skip generating the summary plot.")
    parser.add_argument("--show", action="store_true", help="Also open the plot in an interactive window.")
    parser.add_argument(
        "--export-map",
        type=str,
        default=None,
        help="Export the final characteristic map to this path (.csv or .json, by extension).",
    )
    parser.add_argument(
        "--import-map",
        type=str,
        default=None,
        help="Resume from a characteristic map previously written by --export-map (.csv or .json).",
    )
    parser.add_argument(
        "--raw-samples",
        action="store_true",
        help="Skip the settling/averaging model and ingest every raw sample directly.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL)
    args = _parse_args()

    data = influx_loader.load_data(args.csv_path) if args.csv_path else None

    resumed_map = None
    if args.import_map:
        resumed_map = CharacteristicMap()
        import_path = Path(args.import_map)
        if import_path.suffix.lower() == ".json":
            resumed_map.import_json(import_path)
        else:
            resumed_map.import_csv(import_path)
        print(f"Resumed characteristic map from {import_path} ({len(resumed_map.all_cells())} cells)")

    result = run_simulation(
        df=data, use_stable_periods=not args.raw_samples, initial_map=resumed_map
    )

    print(f"Characteristic map cells: {len(result.characteristic_map.all_cells())}")
    print(f"Mean |spread error|: {result.spread_error_series.abs().mean():.3f} K  (primary — secondary ΔT)")
    print(f"Mean COP (logged, not optimized): {result.cop_series.mean():.2f}")
    print(f"Final active-cell fraction: {result.active_cell_fraction_over_time.iloc[-1]:.2%}")

    if args.export_map:
        export_path = Path(args.export_map)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        if export_path.suffix.lower() == ".json":
            result.characteristic_map.export_json(export_path)
        else:
            result.characteristic_map.export_csv(export_path)
        print(f"Characteristic map exported to {export_path}")

    if not args.no_plot:
        from .plotting import plot_simulation_summary

        plot_path = Path(args.plot_output)
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plot_simulation_summary(result, save_path=plot_path)
        print(f"Summary plot saved to {plot_path}")

        if args.show:
            import matplotlib.pyplot as plt

            plt.show()
