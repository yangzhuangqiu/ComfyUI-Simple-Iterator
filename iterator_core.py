import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict


_LOGGER = logging.getLogger("ComfyUI.SimpleIterator.Core")


def _sha1(parts) -> str:
    """对输入片段做稳定哈希，生成可持久化的短键。"""
    digest = hashlib.sha1()
    for part in parts:
        digest.update(str(part).encode("utf-8", errors="ignore"))
        digest.update(b"\x00")
    return digest.hexdigest()


def stable_scope(kind: str, unique_id: str, source_key: str) -> str:
    """基于节点与数据源信息生成状态作用域键。"""
    return _sha1((kind, unique_id or "default", source_key))


def format_output_filename(path: Path, with_ext: bool) -> str:
    """根据开关返回文件名（带后缀或不带后缀）。"""
    return path.name if with_ext else path.stem


class IteratorStateStore:
    """定义迭代游标的持久化存取契约。

    典型调用场景:
    - 节点执行前查询当前游标位置（`peek_cursor`）。
    - 节点执行时原子领取当前索引并推进游标（`claim_index`）。
    """

    _lock = threading.Lock()
    _loaded = False
    _state: Dict[str, Dict[str, int]] = {}
    _state_file = Path(__file__).resolve().parent / ".iterator_state.json"
    _config_file = Path(__file__).resolve().parent / "iterator_config.json"
    _env_ttl_key = "SIMPLE_ITERATOR_STATE_TTL_SECONDS"
    _env_max_key = "SIMPLE_ITERATOR_STATE_MAX_ENTRIES"
    _default_ttl_seconds = 30 * 24 * 60 * 60
    _default_max_entries = 2000
    _ttl_seconds = _default_ttl_seconds
    _max_entries = _default_max_entries

    @classmethod
    def _parse_int(
        cls,
        *,
        value,
        default: int,
        min_value: int,
        source: str,
        key: str,
    ) -> int:
        """将配置值解析为整数并做范围保护。"""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Invalid %s '%s' from %s; fallback to default=%s",
                key,
                value,
                source,
                default,
            )
            return default
        if parsed < min_value:
            _LOGGER.warning(
                "Out-of-range %s=%s from %s; require >= %s, fallback to default=%s",
                key,
                parsed,
                source,
                min_value,
                default,
            )
            return default
        return parsed

    @classmethod
    def _load_gc_settings(cls) -> None:
        """加载状态清理配置（默认值 < JSON 文件 < 环境变量）。"""
        ttl_value = cls._default_ttl_seconds
        max_value = cls._default_max_entries

        file_settings = {}
        if cls._config_file.exists():
            try:
                raw = json.loads(cls._config_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    file_settings = raw
                else:
                    _LOGGER.warning(
                        "Invalid config root in %s; expected object, got %s. Using defaults.",
                        cls._config_file,
                        type(raw).__name__,
                    )
            except (json.JSONDecodeError, OSError) as err:
                _LOGGER.warning(
                    "Failed to read config file %s: %s. Using defaults.",
                    cls._config_file,
                    err,
                )

        if "state_ttl_seconds" in file_settings:
            ttl_value = cls._parse_int(
                value=file_settings["state_ttl_seconds"],
                default=cls._default_ttl_seconds,
                min_value=0,
                source=f"file:{cls._config_file}",
                key="state_ttl_seconds",
            )
        if "state_max_entries" in file_settings:
            max_value = cls._parse_int(
                value=file_settings["state_max_entries"],
                default=cls._default_max_entries,
                min_value=1,
                source=f"file:{cls._config_file}",
                key="state_max_entries",
            )

        env_ttl = os.getenv(cls._env_ttl_key)
        if env_ttl is not None:
            ttl_value = cls._parse_int(
                value=env_ttl,
                default=ttl_value,
                min_value=0,
                source=f"env:{cls._env_ttl_key}",
                key="state_ttl_seconds",
            )
        env_max = os.getenv(cls._env_max_key)
        if env_max is not None:
            max_value = cls._parse_int(
                value=env_max,
                default=max_value,
                min_value=1,
                source=f"env:{cls._env_max_key}",
                key="state_max_entries",
            )

        cls._ttl_seconds = ttl_value
        cls._max_entries = max_value

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return
        cls._load_gc_settings()
        if cls._state_file.exists():
            try:
                cls._state = json.loads(cls._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cls._state = {}
        else:
            cls._state = {}
        pruned = cls._prune_state()
        cls._loaded = True
        if pruned:
            cls._save()

    @classmethod
    def _save(cls) -> None:
        cls._prune_state()
        payload = json.dumps(cls._state, ensure_ascii=False, indent=2)
        cls._state_file.write_text(payload, encoding="utf-8")

    @classmethod
    def _prune_state(cls, now_ts: int | None = None) -> bool:
        """按保留策略清理状态条目，避免状态文件无限增长。

        语义:
        - 先删除超过 TTL 未更新的条目，再执行最大条目数裁剪。
        - 无效条目（非字典）会被直接移除。

        返回:
        - `True`: 状态有变更（发生清理）。
        - `False`: 状态无变更。
        """
        if not isinstance(cls._state, dict):
            cls._state = {}
            return True

        changed = False
        now_value = int(time.time()) if now_ts is None else int(now_ts)
        ttl = max(int(cls._ttl_seconds), 0)
        max_entries = max(int(cls._max_entries), 1)

        # 语义: TTL 清理优先于容量裁剪，先清掉长期无活跃条目。
        if ttl > 0:
            expired_keys = []
            for key, entry in cls._state.items():
                if not isinstance(entry, dict):
                    expired_keys.append(key)
                    continue
                updated_at = int(entry.get("updated_at", 0) or 0)
                if (now_value - updated_at) > ttl:
                    expired_keys.append(key)
            if expired_keys:
                for key in expired_keys:
                    cls._state.pop(key, None)
                changed = True
        else:
            invalid_keys = [key for key, entry in cls._state.items() if not isinstance(entry, dict)]
            if invalid_keys:
                for key in invalid_keys:
                    cls._state.pop(key, None)
                changed = True

        # 说明: 当条目超过上限时，按 updated_at 新到旧保留最近 N 条。
        if len(cls._state) > max_entries:
            ranked = sorted(
                cls._state.items(),
                key=lambda item: int(item[1].get("updated_at", 0) or 0),
                reverse=True,
            )
            cls._state = dict(ranked[:max_entries])
            changed = True

        return changed

    @classmethod
    def peek_cursor(cls, scope_key: str) -> int:
        """读取当前作用域的游标位置（不推进状态）。

        参数:
        - `scope_key`: 由节点类型、节点唯一标识、数据源键组合出的作用域键。

        返回:
        - 当前游标值，不存在时返回 `0`。
        """
        with cls._lock:
            cls._ensure_loaded()
            entry = cls._state.get(scope_key, {})
            return int(entry.get("cursor", 0))

    @classmethod
    def claim_index(
        cls,
        *,
        scope_key: str,
        total: int,
        reset: bool,
        loop_mode: str,
    ) -> int:
        """原子领取当前索引并按策略推进游标。

        参数:
        - `scope_key`: 迭代状态作用域键。
        - `total`: 当前可迭代元素总数，必须大于 `0`。
        - `reset`: 沿触发复位信号；仅在 `False -> True` 边沿时从 `0` 重新开始。
        - `loop_mode`: 迭代耗尽行为，支持 `loop/stop/hold_last`。

        返回:
        - 本次应输出的索引（推进前索引）。
        """
        if total <= 0:
            raise ValueError("total must be greater than zero")

        with cls._lock:
            cls._ensure_loaded()
            entry = cls._state.get(scope_key, {})
            prev_reset = bool(entry.get("last_reset", False))
            reset_edge = bool(reset) and (not prev_reset)
            cursor = 0 if reset_edge else int(entry.get("cursor", 0))

            if cursor < 0:
                cursor = 0

            # 语义: 当游标越界时，先根据 loop_mode 决定“当前输出索引”如何收敛。
            # 优先级: reset 结果 > loop_mode 越界策略 > 默认顺序推进。
            if cursor >= total:
                if loop_mode == "loop":
                    cursor = 0
                elif loop_mode == "hold_last":
                    cursor = total - 1
                elif loop_mode == "stop":
                    raise RuntimeError(
                        "Iterator exhausted. Set loop_mode=loop/hold_last or enable reset."
                    )
                else:
                    raise ValueError(f"Unsupported loop_mode: {loop_mode}")

            emit_index = cursor

            # 语义: 输出后计算“下一次执行”的游标。
            # 说明: stop 模式会把游标推进到 total 之外，用于下次触发耗尽错误。
            if loop_mode == "loop":
                next_cursor = (cursor + 1) % total
            elif loop_mode == "hold_last":
                next_cursor = min(cursor + 1, total - 1)
            elif loop_mode == "stop":
                next_cursor = cursor + 1
            else:
                raise ValueError(f"Unsupported loop_mode: {loop_mode}")

            cls._state[scope_key] = {
                "cursor": next_cursor,
                "total": total,
                "last_reset": bool(reset),
                "updated_at": int(time.time()),
            }
            cls._save()
            return emit_index
