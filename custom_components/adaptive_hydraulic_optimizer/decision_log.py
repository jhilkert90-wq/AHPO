"""Persistent decision log for the Adaptive Hydraulic Pump Optimizer.

Each time the algorithm proposes a new pump speed a structured JSON line is
appended to a .jsonl file in Home Assistant's .storage directory.  The file
can be inspected via the HA File Editor add-on to understand *why* every
speed change was made.

Enable / disable via the "decision_log_enabled" option in the integration's
Options Flow.  When disabled no file is created or written and the overhead
is zero.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DECISION_LOG_STORAGE_KEY = "adaptive_hydraulic_optimizer_decisions"
_DEFAULT_MAX_LINES = 10_000


class DecisionLogger:
    """Append-only JSONL writer for pump-speed-change decisions.

    All file I/O is offloaded to the executor so the HA event loop is never
    blocked.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        storage_dir = Path(hass.config.path(".storage"))
        self._path = storage_dir / f"{DECISION_LOG_STORAGE_KEY}_{entry_id}.jsonl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def async_log(self, entry: dict[str, Any]) -> None:
        """Append one decision entry (dict) as a JSON line.  Non-blocking."""
        await self._hass.async_add_executor_job(self._write_line, entry)

    async def async_rotate(self, max_lines: int = _DEFAULT_MAX_LINES) -> None:
        """Trim the log to at most *max_lines* newest entries.  Non-blocking."""
        await self._hass.async_add_executor_job(self._rotate, max_lines)

    # ------------------------------------------------------------------
    # Blocking helpers (run in executor)
    # ------------------------------------------------------------------

    def _write_line(self, entry: dict[str, Any]) -> None:
        """Serialise *entry* as JSON and append it as a single line."""
        try:
            line = json.dumps(entry, default=str) + "\n"
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            _LOGGER.exception("Decision log: failed to write to %s", self._path)

    def _rotate(self, max_lines: int) -> None:
        """Keep only the last *max_lines* lines in the log file."""
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines(keepends=True)
            if len(lines) > max_lines:
                trimmed = lines[-max_lines:]
                # Write atomically via a temp file.
                tmp = self._path.with_suffix(".jsonl.tmp")
                tmp.write_text("".join(trimmed), encoding="utf-8")
                os.replace(tmp, self._path)
        except OSError:
            _LOGGER.exception("Decision log: failed to rotate %s", self._path)


# ------------------------------------------------------------------
# Helper: build a decision entry from coordinator / learning context
# ------------------------------------------------------------------

def build_decision_entry(
    *,
    timestamp: datetime,
    operating_mode: str,
    outdoor_temp_bin: float,
    compressor_freq_bin: float,
    previous_speed: float | None,
    proposed_speed: float,
    spread_error_at_current: float,
    best_abs_spread_error: float,
    cop_at_current: float,
    cop_mean_logged: float,
    n_measurements: int,
    phase: str,
    hill_climb_direction: int,
    hill_climb_step_size: float,
    hill_climb_reversals: int,
    hill_climb_improved: bool,
) -> dict[str, Any]:
    """Construct a structured log entry and populate the human-readable *reason* field."""

    if previous_speed is None:
        reason = "First speed write for this session."
    elif not hill_climb_improved and hill_climb_reversals == 0 and hill_climb_step_size > 0:
        direction_str = "up" if hill_climb_direction > 0 else "down"
        reason = (
            f"First observation for this cell; "
            f"starting hill-climb {direction_str} with step {hill_climb_step_size:.1f}%."
        )
    elif hill_climb_improved:
        direction_str = "up" if hill_climb_direction > 0 else "down"
        prev_abs = abs(spread_error_at_current)
        reason = (
            f"Spread error improved (|e| decreased to {prev_abs:.3f} K); "
            f"continuing {direction_str} by {hill_climb_step_size:.1f}% "
            f"({hill_climb_reversals} reversals so far)."
        )
    else:
        direction_str = "up" if hill_climb_direction > 0 else "down"
        reason = (
            f"Spread error did not improve (|e| = {abs(spread_error_at_current):.3f} K); "
            f"reversed direction, halved step to {hill_climb_step_size:.1f}%, "
            f"now going {direction_str} "
            f"({hill_climb_reversals} reversals so far)."
        )

    return {
        "timestamp": timestamp.isoformat(),
        "operating_mode": operating_mode,
        "outdoor_temp_bin": outdoor_temp_bin,
        "compressor_freq_bin": compressor_freq_bin,
        "previous_speed": previous_speed,
        "proposed_speed": proposed_speed,
        "spread_error_at_current": spread_error_at_current,
        "best_abs_spread_error": best_abs_spread_error if math.isfinite(best_abs_spread_error) else None,
        "cop_at_current": cop_at_current,
        "cop_mean_logged": cop_mean_logged,
        "n_measurements": n_measurements,
        "phase": phase,
        "hill_climb_direction": hill_climb_direction,
        "hill_climb_step_size": hill_climb_step_size,
        "hill_climb_reversals": hill_climb_reversals,
        "hill_climb_improved": hill_climb_improved,
        "reason": reason,
    }
