# Memory Bank

- Current repository version: 2026.09.2
- Last synchronized: 2026-09-27T14:21:37.359383+00:00

## Product behavior

- AHPO optimizes the signed spread error `ΔT_primary − ΔT_secondary`; COP/EER is logged for visibility but does not drive the optimizer.
- The Home Assistant config flow requires a measured charge-pump-speed input and optionally accepts a separate writable setpoint output.

## Repository structure

- `custom_components/adaptive_hydraulic_optimizer/` contains the Home Assistant integration.
- `ahpo_sim/` contains the simulator and automated tests.
- `scripts/sync_repo_metadata.py` synchronizes `VERSION`, `CHANGELOG.md`, this memory bank, and the README version line.

## Release bookkeeping

- Version format: `year.month.update_number_for_that_month`.
- Run `python scripts/sync_repo_metadata.py` after tracked repository changes, or let CI enforce it with `--check`.
