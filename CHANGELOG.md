# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-03-30

### Added
- Added release quality gate script `scripts/release_gate.py` for version/lint/core-test checks.
- Added GitHub Actions workflow `.github/workflows/quality-gate.yml`.
- Added test layering with `tests/core` and optional `tests/runtime`.
- Added `tests/runtime/test_runtime_smoke.py` for runtime-layer smoke validation.
- Added `iterator_config.example.json` for local state GC overrides.

### Changed
- Bumped package version to `0.1.1`.
- Updated root import behavior to support core tests without runtime deps via env gate.
- Updated README and README.zh-CN testing guidance to reflect layered testing and release gate.
- Added `dev` optional dependency group in `pyproject.toml` (`pytest`, `ruff`).
- Reorganized core tests from `tests/test_iterator_core.py` to `tests/core/test_iterator_core.py`.
- Added `iterator_config.json` to `.gitignore` for local-only GC overrides.
- Added state file growth protection for `.iterator_state.json`:
  - TTL-based cleanup for stale entries.
  - Max-entry cap to keep only the most recently updated states.
  - GC policy configurable via `iterator_config.json` and environment variables.

### Upgrade Notes
- If a scope entry is removed by TTL cleanup or max-entry pruning, its cursor restarts from index `0` on next run.
- Default GC values:
  - `state_ttl_seconds = 2592000` (30 days)
  - `state_max_entries = 2000`

## [0.1.0] - 2026-03-28

### Added
- Added persistent iterator state with scope isolation by node id and source key.
- Added `Iterator Load Image` with one-sample-per-run behavior and file name output.
- Added `Iterator Load Video Path` with one-sample-per-run behavior and file name output.
- Added `Iterator Load Text From Dir` and `Iterator Load Text From File`.
- Added loop modes: `loop`, `stop`, and `hold_last`.
- Added edge-triggered reset behavior (`False -> True` only).
- Added runtime state ignore rule for `.iterator_state.json`.
- Added minimal tests for sequence progression, stop mode, edge reset, and filename output behavior.

### Changed
- Split text loading into two dedicated nodes and removed the combined text node.
- Updated defaults for image/video/text patterns and loop behavior to safer batch-processing defaults.
- Expanded inline node documentation and README usage details.
