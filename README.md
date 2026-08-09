# Adaptive Hydraulic Pump Optimizer (AHPO)

A Home Assistant integration that learns the optimal charge-pump speed for hydraulically
decoupled heating/cooling systems (buffer tank / hydraulic separator) by minimizing the
**spread error** `e = ΔT_primary − ΔT_secondary` across the hydraulic separator.

Not a PID controller. Not a temperature controller. It builds a characteristic map
(outdoor temperature × compressor frequency → optimal pump speed) from observed behavior,
then fine-tunes it online with hill climbing once enough confidence has been built up for a
given operating point. COP/EER is computed and logged as a byproduct — it is no longer the
optimization target (COP is confounded by compressor frequency and absolute temperature level,
variables the charge pump cannot control).

## Status

Pre-release skeleton (Home Assistant integration Milestones 1-4 implemented; not yet
validated on a real system). See `Adaptive hydraulic pump optimizer v2.md` for the full
project spec, and `ahpo_sim/` for the historical-data simulator used to design and test
the optimization core before wiring it into Home Assistant.

## Two parts of this repository

- **`ahpo_sim/`** - standalone Python simulator (no Home Assistant dependency) that
  replays historical InfluxDB/CSV export data to validate the spread-error calculation,
  characteristic map, Phase A/B transition logic, and the hill-climbing optimizer.
  See "Running the simulator" below.
- **`custom_components/adaptive_hydraulic_optimizer/`** - the actual Home Assistant
  (HACS-installable) integration, built on the same optimization core.

## Core idea: Phase A / Phase B

- **Phase A (passive/shadow mode)**: AHPO only observes your heat pump's native pump
  control and builds the characteristic map from real operating data - it never writes
  the pump speed.
- **Phase B (active optimization)**: AHPO takes over the charge-pump speed and runs
  hill climbing to fine-tune it, per characteristic-map cell.
- The switch from A to B is **manual** in this integration (via the "Phase override"
  select entity, or the `set_phase_override` service) - there is no automatic detection
  of "native control active", since not every heat pump exposes such a signal.

## Installation (HACS)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install "Adaptive Hydraulic Pump Optimizer" and restart Home Assistant.
3. Go to **Settings -> Devices & Services -> Add Integration** and search for it.
4. In the config flow, map each required signal to an existing entity:
   - Primary flow/return temperature, primary flow rate
   - **Secondary flow/return temperature** (buffer/separator secondary side — required for spread-error calculation)
   - Total electrical power, compressor frequency, outdoor temperature
   - Charge pump speed (must be a writable `number` or `input_number` entity)
   - Operating mode (`heat` or `cool` text state only), error status

### Operating mode requirement

- AHPO only calculates/optimizes when operating mode is exactly `heat` or `cool`.
- Any other operating-mode state pauses calculation/optimization for that tick until
  the mode returns to `heat` or `cool`.
- The spread error `e = ΔT_primary − ΔT_secondary` is signed: `e > 0` means the pump
  is too slow (primary spreads more than secondary → mixing loss); `e < 0` means too fast.
  The optimizer drives `e` toward zero. COP/EER is computed using `abs(VL-RL)` and logged
  per cell as an informational byproduct — it no longer influences the optimization target,
  confidence formula, or map weighting.

## Entities provided

- **Sensors**: spread error (`e = ΔT_primary − ΔT_secondary`, the optimization target),
  current COP (log), averaged COP (log), optimal charge pump speed, confidence score,
  operating phase, active-cell fraction
- **Select**: Phase override (automatic / passive / active)
- **Number**: confidence threshold (Phase A -> B)
- **Buttons**: reset characteristic map, reset confidence

## Services

- `reset_characteristic_map`, `reset_confidence`
- `set_phase_override` (`automatic` / `passive` / `active`)
- `export_characteristic_map` (writes the learned map to a JSON file)

## Safety fallbacks

AHPO automatically falls back to Phase A (passive) if:
- a mapped sensor becomes unavailable,
- the mapped error-status entity turns on, or
- writing the charge-pump-speed entity fails (e.g. lost write permission) -
  it recovers automatically once writes succeed again.

## Running the simulator

```powershell
python -m ahpo_sim.simulate --export-map ahpo_sim/output/characteristic_map.csv
```

See `ahpo_sim/config.py` for all tunable parameters (column mapping, settling/averaging
timing, confidence thresholds, optimizer step sizes).

For simulation data, operating mode must resolve to `heat` or `cool` (or supported
numeric mode codes mapped in `ahpo_sim/config.py`); rows with other mode values are skipped.

## Development

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
pytest -q
```

## License

Not yet specified - add a `LICENSE` file before publishing this repository publicly.
