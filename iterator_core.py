import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Dict


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

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return
        if cls._state_file.exists():
            try:
                cls._state = json.loads(cls._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cls._state = {}
        else:
            cls._state = {}
        cls._loaded = True

    @classmethod
    def _save(cls) -> None:
        payload = json.dumps(cls._state, ensure_ascii=False, indent=2)
        cls._state_file.write_text(payload, encoding="utf-8")

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
