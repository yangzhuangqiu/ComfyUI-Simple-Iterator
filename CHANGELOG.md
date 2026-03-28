# Changelog

All notable changes to this project will be documented in this file.

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
