"""Matplotlib visualizations for a simulation run: COP trace, characteristic-map heatmap,
Phase-B rollout over time, and optimizer convergence.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .characteristic_map import CharacteristicMap, characteristic_map_heatmap

if TYPE_CHECKING:
    from .simulate import SimulationResult


def plot_cop_series(cop_series: pd.Series, rolling_window: int = 100, ax: Axes | None = None) -> Axes:
    """Raw COP samples plus a rolling mean to show the overall trend."""
    if ax is None:
        _, ax = plt.subplots()
    ax.plot(cop_series.index, cop_series.values, ".", markersize=1, alpha=0.3, label="COP (raw)")
    if len(cop_series) >= 2:
        window = min(rolling_window, len(cop_series))
        rolling = cop_series.rolling(window, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, linewidth=1.5, label=f"COP (rolling mean, n={window})")
    ax.set_title("COP over time")
    ax.set_xlabel("Time")
    ax.set_ylabel("COP")
    ax.legend(loc="upper right", fontsize="small")
    return ax


def plot_characteristic_map_heatmap(
    characteristic_map: CharacteristicMap, value: str = "best_cop", ax: Axes | None = None
) -> Axes:
    """Outdoor-temp x compressor-frequency heatmap of the requested characteristic-map metric."""
    if ax is None:
        _, ax = plt.subplots()
    table = characteristic_map_heatmap(characteristic_map, value=value)
    if table.empty:
        ax.set_title(f"Characteristic map ({value}) - no data")
        return ax

    table = table.sort_index().sort_index(axis=1)
    image = ax.imshow(table.values, aspect="auto", origin="lower", cmap="viridis")
    ax.set_xticks(range(len(table.columns)))
    ax.set_xticklabels([f"{c:g}" for c in table.columns], rotation=45, ha="right")
    ax.set_yticks(range(len(table.index)))
    ax.set_yticklabels([f"{i:g}" for i in table.index])
    ax.set_xlabel("Compressor frequency [Hz]")
    ax.set_ylabel("Outdoor temperature [°C]")
    ax.set_title(f"Characteristic map heatmap ({value})")
    ax.figure.colorbar(image, ax=ax)
    return ax


def plot_optimal_speed_heatmap(characteristic_map: CharacteristicMap, ax: Axes | None = None) -> Axes:
    """Outdoor-temp x compressor-frequency heatmap of the learned optimal charge-pump speed."""
    if ax is None:
        _, ax = plt.subplots()
    ax = plot_characteristic_map_heatmap(characteristic_map, value="optimal_charge_pump_speed", ax=ax)
    ax.set_title("Characteristic map: optimal charge-pump speed [%]")
    return ax


def plot_active_cell_fraction(active_cell_fraction_over_time: pd.Series, ax: Axes | None = None) -> Axes:
    """Share of characteristic-map cells released for Phase B, over time."""
    if ax is None:
        _, ax = plt.subplots()
    ax.plot(active_cell_fraction_over_time.index, active_cell_fraction_over_time.values * 100.0)
    ax.set_title("Share of cells released for Phase B")
    ax.set_xlabel("Time")
    ax.set_ylabel("Phase B share [%]")
    ax.set_ylim(0, 100)
    return ax


def plot_optimizer_convergence(
    optimizer_traces: dict[tuple[float, float], list[tuple[float, float]]],
    ax: Axes | None = None,
    max_cells: int = 8,
) -> Axes:
    """COP per hill-climbing step for the most active characteristic-map cells (convergence check)."""
    if ax is None:
        _, ax = plt.subplots()
    traces_by_length = sorted(optimizer_traces.items(), key=lambda item: len(item[1]), reverse=True)
    if not traces_by_length:
        ax.set_title("Optimizer convergence - no active cells")
        return ax

    for (outdoor_temp_bin, compressor_freq_bin), history in traces_by_length[:max_cells]:
        cop_values = [cop for _, cop in history]
        ax.plot(
            range(1, len(cop_values) + 1),
            cop_values,
            marker="o",
            markersize=3,
            label=f"AT={outdoor_temp_bin:g}°C, Hz={compressor_freq_bin:g}",
        )
    ax.set_title("Optimizer convergence (COP per hill-climbing step)")
    ax.set_xlabel("Step")
    ax.set_ylabel("COP")
    ax.legend(fontsize="x-small", loc="best")
    return ax


def plot_simulation_summary(result: "SimulationResult", save_path: str | Path | None = None) -> Figure:
    """2x3 overview figure: COP trace, characteristic-map heatmaps (COP + optimal speed),
    Phase-B rollout, and optimizer convergence."""
    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    plot_cop_series(result.cop_series, ax=axes[0, 0])
    plot_characteristic_map_heatmap(result.characteristic_map, ax=axes[0, 1])
    plot_optimal_speed_heatmap(result.characteristic_map, ax=axes[0, 2])
    plot_active_cell_fraction(result.active_cell_fraction_over_time, ax=axes[1, 0])
    plot_optimizer_convergence(result.optimizer_traces, ax=axes[1, 1])
    axes[1, 2].axis("off")
    fig.tight_layout()
    if save_path is not None:
        fig.savefig(save_path, dpi=150)
    return fig
