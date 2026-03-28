import shutil
import uuid
from pathlib import Path

import pytest

from iterator_core import IteratorStateStore, format_output_filename, stable_scope


def _reset_store(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    IteratorStateStore._state_file = state_path
    IteratorStateStore._state = {}
    IteratorStateStore._loaded = False


def _state_path() -> Path:
    return Path(__file__).resolve().parent / ".tmp" / f"state-{uuid.uuid4().hex}.json"


def _cleanup(path: Path) -> None:
    if path.parent.exists():
        shutil.rmtree(path.parent, ignore_errors=True)


def test_sequence_progression():
    state_path = _state_path()
    _reset_store(state_path)
    scope = stable_scope("video", "node-a", "source-a")

    indexes = [
        IteratorStateStore.claim_index(scope_key=scope, total=3, reset=False, loop_mode="loop"),
        IteratorStateStore.claim_index(scope_key=scope, total=3, reset=False, loop_mode="loop"),
        IteratorStateStore.claim_index(scope_key=scope, total=3, reset=False, loop_mode="loop"),
    ]

    assert indexes == [0, 1, 2]
    _cleanup(state_path)


def test_stop_mode_raises_when_exhausted():
    state_path = _state_path()
    _reset_store(state_path)
    scope = stable_scope("video", "node-b", "source-b")

    IteratorStateStore.claim_index(scope_key=scope, total=2, reset=False, loop_mode="stop")
    IteratorStateStore.claim_index(scope_key=scope, total=2, reset=False, loop_mode="stop")

    with pytest.raises(RuntimeError, match="Iterator exhausted"):
        IteratorStateStore.claim_index(scope_key=scope, total=2, reset=False, loop_mode="stop")
    _cleanup(state_path)


def test_reset_edge_trigger():
    state_path = _state_path()
    _reset_store(state_path)
    scope = stable_scope("video", "node-c", "source-c")

    # First run, no reset: output index 0.
    i0 = IteratorStateStore.claim_index(scope_key=scope, total=5, reset=False, loop_mode="loop")
    # Rising edge False -> True: reset once, output index 0.
    i1 = IteratorStateStore.claim_index(scope_key=scope, total=5, reset=True, loop_mode="loop")
    # Keep True: no second reset, should continue to index 1.
    i2 = IteratorStateStore.claim_index(scope_key=scope, total=5, reset=True, loop_mode="loop")
    # Arm the next reset by setting False, then rising edge again.
    IteratorStateStore.claim_index(scope_key=scope, total=5, reset=False, loop_mode="loop")
    i3 = IteratorStateStore.claim_index(scope_key=scope, total=5, reset=True, loop_mode="loop")

    assert (i0, i1, i2, i3) == (0, 0, 1, 0)
    _cleanup(state_path)


def test_filename_output_with_and_without_extension():
    sample = Path("demo_video.mp4")
    assert format_output_filename(sample, True) == "demo_video.mp4"
    assert format_output_filename(sample, False) == "demo_video"
