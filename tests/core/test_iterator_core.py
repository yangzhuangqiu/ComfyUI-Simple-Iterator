import json
import shutil
import uuid
from pathlib import Path

import pytest

from iterator_core import IteratorStateStore, format_output_filename, stable_scope

pytestmark = pytest.mark.core


def _reset_store(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    IteratorStateStore._state_file = state_path
    IteratorStateStore._config_file = state_path.parent / "iterator_config.json"
    IteratorStateStore._state = {}
    IteratorStateStore._loaded = False
    IteratorStateStore._ttl_seconds = IteratorStateStore._default_ttl_seconds
    IteratorStateStore._max_entries = IteratorStateStore._default_max_entries


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


def test_state_prunes_expired_entries_by_ttl():
    state_path = _state_path()
    _reset_store(state_path)
    backup_ttl = IteratorStateStore._ttl_seconds
    backup_max = IteratorStateStore._max_entries

    try:
        IteratorStateStore._ttl_seconds = 10
        IteratorStateStore._max_entries = 100
        now_ts = 1_700_000_000
        IteratorStateStore._state = {
            "stale": {"cursor": 1, "updated_at": now_ts - 100},
            "fresh": {"cursor": 2, "updated_at": now_ts - 5},
        }

        changed = IteratorStateStore._prune_state(now_ts=now_ts)

        assert changed is True
        assert "stale" not in IteratorStateStore._state
        assert "fresh" in IteratorStateStore._state
    finally:
        IteratorStateStore._ttl_seconds = backup_ttl
        IteratorStateStore._max_entries = backup_max
        _cleanup(state_path)


def test_state_prunes_by_max_entries_keep_recent():
    state_path = _state_path()
    _reset_store(state_path)
    backup_ttl = IteratorStateStore._ttl_seconds
    backup_max = IteratorStateStore._max_entries

    try:
        IteratorStateStore._ttl_seconds = 999_999_999
        IteratorStateStore._max_entries = 2
        IteratorStateStore._state = {
            "old": {"cursor": 0, "updated_at": 10},
            "newest": {"cursor": 1, "updated_at": 30},
            "middle": {"cursor": 2, "updated_at": 20},
        }

        changed = IteratorStateStore._prune_state(now_ts=100)

        assert changed is True
        assert set(IteratorStateStore._state.keys()) == {"newest", "middle"}
    finally:
        IteratorStateStore._ttl_seconds = backup_ttl
        IteratorStateStore._max_entries = backup_max
        _cleanup(state_path)


def test_gc_settings_load_from_file():
    state_path = _state_path()
    _reset_store(state_path)
    config_path = IteratorStateStore._config_file
    config_path.write_text(
        json.dumps({"state_ttl_seconds": 123, "state_max_entries": 321}),
        encoding="utf-8",
    )

    try:
        IteratorStateStore._load_gc_settings()
        assert IteratorStateStore._ttl_seconds == 123
        assert IteratorStateStore._max_entries == 321
    finally:
        _cleanup(state_path)


def test_gc_settings_env_overrides_file(monkeypatch):
    state_path = _state_path()
    _reset_store(state_path)
    config_path = IteratorStateStore._config_file
    config_path.write_text(
        json.dumps({"state_ttl_seconds": 123, "state_max_entries": 321}),
        encoding="utf-8",
    )
    monkeypatch.setenv(IteratorStateStore._env_ttl_key, "456")
    monkeypatch.setenv(IteratorStateStore._env_max_key, "654")

    try:
        IteratorStateStore._load_gc_settings()
        assert IteratorStateStore._ttl_seconds == 456
        assert IteratorStateStore._max_entries == 654
    finally:
        _cleanup(state_path)

def test_gc_settings_invalid_values_fallback(monkeypatch):
    state_path = _state_path()
    _reset_store(state_path)
    config_path = IteratorStateStore._config_file
    config_path.write_text(
        json.dumps({"state_ttl_seconds": -1, "state_max_entries": "bad"}),
        encoding="utf-8",
    )
    monkeypatch.setenv(IteratorStateStore._env_ttl_key, "also_bad")
    monkeypatch.setenv(IteratorStateStore._env_max_key, "-9")

    try:
        IteratorStateStore._load_gc_settings()
        assert IteratorStateStore._ttl_seconds == IteratorStateStore._default_ttl_seconds
        assert IteratorStateStore._max_entries == IteratorStateStore._default_max_entries
    finally:
        _cleanup(state_path)




