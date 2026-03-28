import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import torch
from PIL import Image, ImageOps

from .iterator_core import IteratorStateStore, format_output_filename, stable_scope


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".flv",
}
TEXT_EXTENSIONS = {".txt", ".md", ".prompt", ".json", ".jsonl"}

LOOP_MODES = ("loop", "stop", "hold_last")
ORDER_MODES = ("name_asc", "name_desc", "mtime_asc", "mtime_desc")


_LOGGER = logging.getLogger("ComfyUI.SimpleIterator")
if not _LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[SimpleIterator] %(message)s"))
    _LOGGER.addHandler(_handler)
_LOGGER.propagate = False
_LOGGER.setLevel(logging.INFO)
_LOG_VALUE_MAX_CHARS = 64


def _node_log(enabled: bool, message: str, *args) -> None:
    """按需输出节点调试日志，默认关闭避免刷屏。"""
    if not enabled:
        return
    _LOGGER.info(message, *args)


def _format_log_value(value) -> str:
    """将任意参数值格式化为日志文本，并在超过上限时截断。"""
    if isinstance(value, torch.Tensor):
        rendered = f"Tensor(shape={tuple(value.shape)}, dtype={value.dtype})"
    elif isinstance(value, Path):
        rendered = str(value)
    else:
        try:
            rendered = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            rendered = repr(value)

    if len(rendered) <= _LOG_VALUE_MAX_CHARS:
        return rendered
    return rendered[: _LOG_VALUE_MAX_CHARS - 3] + "..."


def _log_params(enabled: bool, node_name: str, phase: str, payload: dict) -> None:
    """输出节点参数日志，phase 支持 inputs/outputs。"""
    if not enabled:
        return
    formatted = ", ".join(
        f"{key}={_format_log_value(value)}" for key, value in payload.items()
    )
    _node_log(enabled, "[%s] %s: %s", node_name, phase, formatted)


def _normalize_path(path: str) -> Path:
    """将用户输入路径规范化为绝对路径。"""
    return Path(path).expanduser().resolve()


def _split_patterns(pattern: str) -> List[str]:
    """将逗号/分号分隔的通配符字符串拆分为模式列表。"""
    value = (pattern or "").strip()
    if not value:
        return ["*"]
    patterns = []
    for token in value.replace(";", ",").split(","):
        token = token.strip()
        if token:
            patterns.append(token)
    return patterns or ["*"]


def _filter_and_collect(
    directory: str,
    pattern: str,
    recursive: bool,
    extensions: set,
    order: str,
) -> List[Path]:
    """按通配符、扩展名和排序策略收集文件。"""
    root = _normalize_path(directory)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    files = {}
    patterns = _split_patterns(pattern)
    for item in patterns:
        iterator = root.rglob(item) if recursive else root.glob(item)
        for path in iterator:
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            key = str(path.resolve()).lower()
            files[key] = path.resolve()

    collected = list(files.values())

    if order == "name_asc":
        collected.sort(key=lambda p: p.name.lower())
    elif order == "name_desc":
        collected.sort(key=lambda p: p.name.lower(), reverse=True)
    elif order == "mtime_asc":
        collected.sort(key=lambda p: (p.stat().st_mtime_ns, p.name.lower()))
    elif order == "mtime_desc":
        collected.sort(key=lambda p: (p.stat().st_mtime_ns, p.name.lower()), reverse=True)
    else:
        raise ValueError(f"Unsupported order mode: {order}")

    return collected


def _fingerprint_paths(paths: List[Path]) -> str:
    """根据路径与文件元数据生成稳定指纹。"""
    digest = hashlib.sha1()
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(str(path).encode("utf-8", errors="ignore"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _load_image_tensor(path: Path):
    """把图片文件转换为 ComfyUI 需要的 IMAGE/MASK 张量。"""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        rgb = img.convert("RGB")
        array = np.array(rgb).astype(np.float32) / 255.0
        image = torch.from_numpy(array)[None,]

        if "A" in img.getbands():
            alpha = np.array(img.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(alpha)
        else:
            width, height = rgb.size
            mask = torch.zeros((height, width), dtype=torch.float32)

    return image, mask


def _decode_delimiter(value: str) -> str:
    """解码用户输入的转义分隔符（如 `\\n---\\n`）。"""
    if value is None:
        return ""
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return value


def _file_fingerprint(path: Path) -> str:
    """生成单文件指纹（路径 + mtime + size）。"""
    stat = path.stat()
    payload = f"{path}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _scan_text_files(
    directory: Path, pattern: str = "*", recursive: bool = True, order: str = "name_asc"
) -> List[Path]:
    """按通配符、递归策略和排序策略扫描目录内受支持的文本文件。"""
    files = {}
    patterns = _split_patterns(pattern)
    for item in patterns:
        iterator = directory.rglob(item) if recursive else directory.glob(item)
        for path in iterator:
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            key = str(path.resolve()).lower()
            files[key] = path.resolve()

    paths = list(files.values())
    if order == "name_asc":
        paths.sort(key=lambda p: (p.name.lower(), str(p).lower()))
    elif order == "name_desc":
        paths.sort(key=lambda p: (p.name.lower(), str(p).lower()), reverse=True)
    elif order == "mtime_asc":
        paths.sort(key=lambda p: (p.stat().st_mtime_ns, p.name.lower(), str(p).lower()))
    elif order == "mtime_desc":
        paths.sort(
            key=lambda p: (p.stat().st_mtime_ns, p.name.lower(), str(p).lower()), reverse=True
        )
    else:
        raise ValueError(f"Unsupported order mode: {order}")
    return paths


def _extract_json_field(entry, json_field: str) -> str:
    """从 JSON 元素中提取输出文本内容。"""
    if isinstance(entry, str):
        return entry

    if json_field:
        value = entry
        # 语义: `a.b.c` 表示逐层字典取值。
        # 说明: 任意层不存在时直接抛错，避免静默返回错误结果。
        for part in json_field.split("."):
            if not isinstance(value, dict) or part not in value:
                raise KeyError(f"json_field '{json_field}' not found in item: {entry}")
            value = value[part]
    else:
        value = entry

    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


@dataclass
class TextItem:
    # 必填: true；来源: 文本源解析结果；用途: 下游模型/节点输入字符串。
    text: str
    # 必填: true；来源: 文件路径或逻辑切片位置；用途: 追踪样本来源。
    source_path: str


def _load_text_items_from_dir(
    directory: str,
    pattern: str,
    recursive: bool,
    order: str,
    encoding: str,
) -> List[TextItem]:
    """从文本目录加载条目，每个文件整体作为一个条目。"""
    source = _normalize_path(directory)
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Text directory not found: {source}")

    items = []
    for path in _scan_text_files(source, pattern=pattern, recursive=recursive, order=order):
        text = path.read_text(encoding=encoding, errors="replace")
        items.append(TextItem(text=text, source_path=str(path)))
    return items


def _load_text_items_from_file(
    file_path: str,
    parse_mode: str,
    delimiter: str,
    json_field: str,
    encoding: str,
) -> List[TextItem]:
    """从单个文本文件加载条目，支持分隔符与 JSON 结构解析。"""
    source = _normalize_path(file_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Text file not found: {source}")

    raw_text = source.read_text(encoding=encoding, errors="replace")
    items = []

    # 语义: 文件模式下由 parse_mode 决定拆分规则。
    # 优先级: parse_mode 显式配置 > 默认 file_split 行为。
    if parse_mode == "file_split":
        sep = _decode_delimiter(delimiter)
        chunks = [raw_text] if sep == "" else raw_text.split(sep)
        for idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            items.append(TextItem(text=chunk, source_path=f"{source}#{idx}"))
    elif parse_mode == "json_array":
        data = json.loads(raw_text)
        if not isinstance(data, list):
            raise ValueError("json_array mode requires a JSON array file.")
        for idx, entry in enumerate(data):
            items.append(
                TextItem(
                    text=_extract_json_field(entry, json_field),
                    source_path=f"{source}#{idx}",
                )
            )
    elif parse_mode == "jsonl":
        for line_no, line in enumerate(raw_text.splitlines(), start=1):
            content = line.strip()
            if not content:
                continue
            entry = json.loads(content)
            items.append(
                TextItem(
                    text=_extract_json_field(entry, json_field),
                    source_path=f"{source}:{line_no}",
                )
            )
    else:
        raise ValueError(f"Unsupported parse_mode: {parse_mode}")

    return items


def _text_dir_source_fingerprint(directory: str, pattern: str, recursive: bool, order: str) -> str:
    """生成目录文本源指纹，用于触发重算与缓存失效。"""
    source = _normalize_path(directory)
    digest = hashlib.sha1()
    digest.update((pattern or "").encode("utf-8"))
    digest.update(str(bool(recursive)).encode("utf-8"))
    digest.update((order or "").encode("utf-8"))

    if not source.exists() or not source.is_dir():
        return digest.hexdigest()

    for path in _scan_text_files(source, pattern=pattern, recursive=recursive, order=order):
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(str(path).encode("utf-8", errors="ignore"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _text_file_source_fingerprint(
    file_path: str,
    parse_mode: str,
    delimiter: str,
    json_field: str,
) -> str:
    """生成单文件文本源指纹，用于触发重算与缓存失效。"""
    source = _normalize_path(file_path)
    digest = hashlib.sha1()
    digest.update(parse_mode.encode("utf-8"))
    digest.update((delimiter or "").encode("utf-8"))
    digest.update((json_field or "").encode("utf-8"))

    if source.exists() and source.is_file():
        digest.update(_file_fingerprint(source).encode("utf-8"))
    return digest.hexdigest()


class IteratorLoadImage:
    """定义图片迭代加载节点契约。

    典型调用场景:
    - 在 Batch Count 下每轮输出一张新图片，复用现有单图工作流。

    输入参数:
    - `directory`: 图片目录路径。
    - `pattern`: 文件匹配通配符，支持 `,`/`;` 分隔多个模式。默认 `*.png,*.jpg,*.jpeg,*.webp`。
    - `recursive`: 是否递归子目录扫描。
    - `order`: 排序方式，`name_asc/name_desc/mtime_asc/mtime_desc`。
    - `loop_mode`: 耗尽策略，默认 `stop`。
      - `loop`: 到最后一张后回到第一张继续。
      - `stop`: 全部处理完后，下一次执行直接报错停止（防止重复处理）。
      - `hold_last`: 到最后一张后，后续一直返回最后一张。
    - `reset`: 沿触发复位信号，仅在 `False->True` 时复位到首项。
    - `load_always`: 控制是否强制每次都执行本节点。
      - `False`（默认）: 走正常缓存判定，输入与游标未变化时可以复用缓存结果。
      - `True`: 忽略缓存判定，每次执行都重新运行节点逻辑。
      - “每次执行”按节点被调度次数算；例如 `Batch Count=10` 通常就是执行 10 次。
    - `enable_log`: 是否输出该节点运行日志（默认 `False`，建议排查问题时打开）。
    - `filename_with_ext`: 输出文件名是否保留后缀。

    输出参数:
    - `IMAGE`: 当前图片张量（RGB）。
    - `MASK`: 当前图片掩码张量。
    - `FILE_PATH`: 当前图片完整路径。
    - `FILE_NAME`: 当前图片文件名（可带或不带后缀）。
    - `INDEX`: 当前输出索引（从 0 开始）。
    - `TOTAL`: 当前可用样本总数。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory": ("STRING", {"default": ""}),
                "pattern": ("STRING", {"default": "*.png,*.jpg,*.jpeg,*.webp"}),
                "recursive": ("BOOLEAN", {"default": False}),
                "order": (ORDER_MODES, {"default": "name_asc"}),
                "loop_mode": (LOOP_MODES, {"default": "stop"}),
                "reset": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "load_always": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
                "enable_log": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
                "filename_with_ext": (
                    "BOOLEAN",
                    {"default": True, "label_on": "with_ext", "label_off": "without_ext"},
                ),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "MASK", "FILE_PATH", "FILE_NAME", "INDEX", "TOTAL")
    FUNCTION = "run"
    CATEGORY = "simple_iterator"
    OUTPUT_IS_LIST = (False, False, False, False, False, False)

    @classmethod
    def IS_CHANGED(
        cls,
        directory,
        pattern="*.png,*.jpg,*.jpeg,*.webp",
        recursive=False,
        order="name_asc",
        loop_mode="stop",
        reset=False,
        load_always=False,
        enable_log=False,
        filename_with_ext=True,
        unique_id=None,
    ):
        """计算节点变更指纹，不执行索引推进。

        语义:
        - `load_always=False`: 返回稳定指纹，允许 ComfyUI 使用缓存。
        - `load_always=True`: 返回 `NaN`，强制本节点每次都执行。
        """
        if load_always:
            return float("NaN")
        try:
            paths = _filter_and_collect(directory, pattern, recursive, IMAGE_EXTENSIONS, order)
            fingerprint = _fingerprint_paths(paths)
        except Exception:
            fingerprint = "invalid"
        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}"
        scope_key = stable_scope("image", unique_id or "", source_key)
        cursor = IteratorStateStore.peek_cursor(scope_key)
        return hash((scope_key, fingerprint, cursor, reset, loop_mode, enable_log))

    def run(
        self,
        directory,
        pattern,
        recursive,
        order,
        loop_mode,
        reset,
        load_always=False,
        enable_log=False,
        filename_with_ext=True,
        unique_id=None,
    ):
        """按游标读取下一张图片并输出路径与进度。"""
        _log_params(
            enable_log,
            "Image",
            "inputs",
            {
                "directory": directory,
                "pattern": pattern,
                "recursive": recursive,
                "order": order,
                "loop_mode": loop_mode,
                "reset": reset,
                "load_always": load_always,
                "filename_with_ext": filename_with_ext,
                "unique_id": unique_id,
            },
        )
        paths = _filter_and_collect(directory, pattern, recursive, IMAGE_EXTENSIONS, order)
        if not paths:
            raise FileNotFoundError(f"No image files found in directory: {directory}")
        _node_log(
            enable_log,
            "[Image] scanned=%s pattern=%s recursive=%s order=%s loop_mode=%s reset=%s",
            len(paths),
            pattern,
            recursive,
            order,
            loop_mode,
            reset,
        )

        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}"
        scope_key = stable_scope("image", unique_id or "", source_key)
        index = IteratorStateStore.claim_index(
            scope_key=scope_key, total=len(paths), reset=reset, loop_mode=loop_mode
        )
        selected = paths[index]
        _node_log(
            enable_log,
            "[Image] picked index=%s/%s file=%s",
            index,
            len(paths) - 1,
            selected,
        )
        image, mask = _load_image_tensor(selected)
        file_name = format_output_filename(selected, filename_with_ext)
        _log_params(
            enable_log,
            "Image",
            "outputs",
            {
                "IMAGE": image,
                "MASK": mask,
                "FILE_PATH": str(selected),
                "FILE_NAME": file_name,
                "INDEX": index,
                "TOTAL": len(paths),
            },
        )
        return image, mask, str(selected), file_name, index, len(paths)


class IteratorLoadVideoPath:
    """定义视频路径迭代节点契约。

    典型调用场景:
    - 每轮输出一个新视频路径，再交给 VHS 等视频节点继续处理。

    输入参数:
    - `directory`: 视频目录路径。
    - `pattern`: 文件匹配通配符，支持 `,`/`;` 分隔多个模式。默认 `*.mp4`。
    - `recursive`: 是否递归子目录扫描。
    - `order`: 排序方式，`name_asc/name_desc/mtime_asc/mtime_desc`。
    - `loop_mode`: 耗尽策略，默认 `stop`，`loop/stop/hold_last`。
    - `reset`: 沿触发复位信号，仅在 `False->True` 时复位到首项。
    - `load_always`: 强制每次运行都视为节点已变化。
    - `enable_log`: 是否输出该节点运行日志（默认 `False`）。
    - `filename_with_ext`: 输出文件名是否保留后缀，默认 `True`。

    输出参数:
    - `VIDEO_PATH`: 当前视频完整路径。
    - `FILE_NAME`: 当前视频文件名（可带或不带后缀）。
    - `INDEX`: 当前输出索引（从 0 开始）。
    - `TOTAL`: 当前可用样本总数。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory": ("STRING", {"default": ""}),
                "pattern": ("STRING", {"default": "*.mp4"}),
                "recursive": ("BOOLEAN", {"default": False}),
                "order": (ORDER_MODES, {"default": "name_asc"}),
                "loop_mode": (LOOP_MODES, {"default": "stop"}),
                "reset": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "load_always": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
                "enable_log": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
                "filename_with_ext": (
                    "BOOLEAN",
                    {"default": True, "label_on": "with_ext", "label_off": "without_ext"},
                ),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("VIDEO_PATH", "FILE_NAME", "INDEX", "TOTAL")
    FUNCTION = "run"
    CATEGORY = "simple_iterator"
    OUTPUT_IS_LIST = (False, False, False, False)

    @classmethod
    def IS_CHANGED(
        cls,
        directory,
        pattern="*.mp4",
        recursive=False,
        order="name_asc",
        loop_mode="stop",
        reset=False,
        load_always=False,
        enable_log=False,
        filename_with_ext=True,
        unique_id=None,
    ):
        """计算节点变更指纹，不执行索引推进。"""
        if load_always:
            return float("NaN")
        try:
            paths = _filter_and_collect(directory, pattern, recursive, VIDEO_EXTENSIONS, order)
            fingerprint = _fingerprint_paths(paths)
        except Exception:
            fingerprint = "invalid"
        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}"
        scope_key = stable_scope("video", unique_id or "", source_key)
        cursor = IteratorStateStore.peek_cursor(scope_key)
        return hash((scope_key, fingerprint, cursor, reset, loop_mode, enable_log))

    def run(
        self,
        directory,
        pattern,
        recursive,
        order,
        loop_mode,
        reset,
        load_always=False,
        enable_log=False,
        filename_with_ext=True,
        unique_id=None,
    ):
        """按游标输出下一条视频路径与进度信息。"""
        _log_params(
            enable_log,
            "Video",
            "inputs",
            {
                "directory": directory,
                "pattern": pattern,
                "recursive": recursive,
                "order": order,
                "loop_mode": loop_mode,
                "reset": reset,
                "load_always": load_always,
                "filename_with_ext": filename_with_ext,
                "unique_id": unique_id,
            },
        )
        paths = _filter_and_collect(directory, pattern, recursive, VIDEO_EXTENSIONS, order)
        if not paths:
            raise FileNotFoundError(f"No video files found in directory: {directory}")
        _node_log(
            enable_log,
            "[Video] scanned=%s pattern=%s recursive=%s order=%s loop_mode=%s reset=%s",
            len(paths),
            pattern,
            recursive,
            order,
            loop_mode,
            reset,
        )

        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}"
        scope_key = stable_scope("video", unique_id or "", source_key)
        index = IteratorStateStore.claim_index(
            scope_key=scope_key, total=len(paths), reset=reset, loop_mode=loop_mode
        )
        selected = paths[index]
        _node_log(
            enable_log,
            "[Video] picked index=%s/%s file=%s",
            index,
            len(paths) - 1,
            selected,
        )
        file_name = format_output_filename(selected, filename_with_ext)
        _log_params(
            enable_log,
            "Video",
            "outputs",
            {
                "VIDEO_PATH": str(selected),
                "FILE_NAME": file_name,
                "INDEX": index,
                "TOTAL": len(paths),
            },
        )
        return str(selected), file_name, index, len(paths)


class IteratorLoadTextFromDir:
    """定义目录文本迭代加载节点契约。

    典型调用场景:
    - 一个目录里有多个文本文件，每轮执行输出一个文件完整内容。

    输入参数:
    - `directory`: 文本目录路径。
    - `pattern`: 文件匹配通配符，支持 `,`/`;` 分隔多个模式。默认 `*.txt,*.md,*.prompt,*.json,*.jsonl`。
    - `recursive`: 是否递归扫描子目录。默认 `False`。
    - `order`: 排序方式，默认 `name_asc`（按文件名升序）。
    - `encoding`: 文件读取编码。
    - `loop_mode`: 耗尽策略，默认 `stop`，`loop/stop/hold_last`。
    - `reset`: 沿触发复位信号，仅在 `False->True` 时复位到首项。
    - `enable_log`: 是否输出该节点运行日志（默认 `False`）。

    输出参数:
    - `TEXT`: 当前文本内容（整个文件内容）。
    - `SOURCE_PATH`: 当前文本文件完整路径。
    - `INDEX`: 当前输出索引（从 0 开始）。
    - `TOTAL`: 当前可用样本总数。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory": ("STRING", {"default": ""}),
                "pattern": ("STRING", {"default": "*.txt,*.md,*.prompt,*.json,*.jsonl"}),
                "recursive": ("BOOLEAN", {"default": False}),
                "order": (ORDER_MODES, {"default": "name_asc"}),
                "encoding": ("STRING", {"default": "utf-8"}),
                "loop_mode": (LOOP_MODES, {"default": "stop"}),
                "reset": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "enable_log": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("TEXT", "SOURCE_PATH", "INDEX", "TOTAL")
    FUNCTION = "run"
    CATEGORY = "simple_iterator"
    OUTPUT_IS_LIST = (False, False, False, False)

    @classmethod
    def IS_CHANGED(
        cls,
        directory,
        pattern="*.txt,*.md,*.prompt,*.json,*.jsonl",
        recursive=False,
        order="name_asc",
        encoding="utf-8",
        loop_mode="stop",
        reset=False,
        enable_log=False,
        unique_id=None,
    ):
        """计算目录文本源变更指纹，不执行索引推进。"""
        try:
            fingerprint = _text_dir_source_fingerprint(directory, pattern, recursive, order)
        except Exception:
            fingerprint = "invalid"

        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}|{encoding}"
        scope_key = stable_scope("text_dir", unique_id or "", source_key)
        cursor = IteratorStateStore.peek_cursor(scope_key)
        return hash((scope_key, fingerprint, cursor, reset, loop_mode, enable_log))

    def run(
        self,
        directory,
        pattern,
        recursive,
        order,
        encoding,
        loop_mode,
        reset,
        enable_log=False,
        unique_id=None,
    ):
        """按游标输出下一条目录文本及来源路径。"""
        _log_params(
            enable_log,
            "TextDir",
            "inputs",
            {
                "directory": directory,
                "pattern": pattern,
                "recursive": recursive,
                "order": order,
                "encoding": encoding,
                "loop_mode": loop_mode,
                "reset": reset,
                "unique_id": unique_id,
            },
        )
        items = _load_text_items_from_dir(
            directory=directory,
            pattern=pattern,
            recursive=recursive,
            order=order,
            encoding=encoding,
        )
        if not items:
            raise ValueError("No text files found in directory with current filter settings.")
        _node_log(
            enable_log,
            "[TextDir] scanned=%s pattern=%s recursive=%s order=%s loop_mode=%s reset=%s",
            len(items),
            pattern,
            recursive,
            order,
            loop_mode,
            reset,
        )

        source_key = f"{_normalize_path(directory)}|{pattern}|{recursive}|{order}|{encoding}"
        scope_key = stable_scope("text_dir", unique_id or "", source_key)
        index = IteratorStateStore.claim_index(
            scope_key=scope_key, total=len(items), reset=reset, loop_mode=loop_mode
        )
        item = items[index]
        _node_log(
            enable_log,
            "[TextDir] picked index=%s/%s source=%s",
            index,
            len(items) - 1,
            item.source_path,
        )
        _log_params(
            enable_log,
            "TextDir",
            "outputs",
            {
                "TEXT": item.text,
                "SOURCE_PATH": item.source_path,
                "INDEX": index,
                "TOTAL": len(items),
            },
        )
        return item.text, item.source_path, index, len(items)


class IteratorLoadTextFromFile:
    """定义单文件文本迭代加载节点契约。

    典型调用场景:
    - 一个文本文件按分隔符切分后，每轮输出一个片段。
    - 一个 JSON 数组或 JSONL 文件，每轮输出一条记录文本。

    输入参数:
    - `file_path`: 单个文本文件路径。
    - `parse_mode`: 解析方式，`file_split/json_array/jsonl`。
    - `delimiter`: `file_split` 分隔符，默认 `\\n---\\n`，支持转义字符。
    - `json_field`: `json_array/jsonl` 对象项提取字段（支持点路径）。
    - `encoding`: 文件读取编码。
    - `loop_mode`: 耗尽策略，默认 `stop`，`loop/stop/hold_last`。
    - `reset`: 沿触发复位信号，仅在 `False->True` 时复位到首项。
    - `enable_log`: 是否输出该节点运行日志（默认 `False`）。

    输出参数:
    - `TEXT`: 当前文本片段或记录内容。
    - `SOURCE_PATH`: 来源位置（`#分片索引` 或 `:行号`）。
    - `INDEX`: 当前输出索引（从 0 开始）。
    - `TOTAL`: 当前可用样本总数。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {"default": ""}),
                "parse_mode": (("file_split", "json_array", "jsonl"), {"default": "file_split"}),
                "delimiter": ("STRING", {"default": "\\n---\\n"}),
                "json_field": ("STRING", {"default": ""}),
                "encoding": ("STRING", {"default": "utf-8"}),
                "loop_mode": (LOOP_MODES, {"default": "stop"}),
                "reset": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "enable_log": (
                    "BOOLEAN",
                    {"default": False, "label_on": "enabled", "label_off": "disabled"},
                ),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("TEXT", "SOURCE_PATH", "INDEX", "TOTAL")
    FUNCTION = "run"
    CATEGORY = "simple_iterator"
    OUTPUT_IS_LIST = (False, False, False, False)

    @classmethod
    def IS_CHANGED(
        cls,
        file_path,
        parse_mode="file_split",
        delimiter="\\n---\\n",
        json_field="",
        encoding="utf-8",
        loop_mode="stop",
        reset=False,
        enable_log=False,
        unique_id=None,
    ):
        """计算单文件文本源变更指纹，不执行索引推进。"""
        try:
            fingerprint = _text_file_source_fingerprint(
                file_path=file_path,
                parse_mode=parse_mode,
                delimiter=delimiter,
                json_field=json_field,
            )
        except Exception:
            fingerprint = "invalid"

        source_key = f"{_normalize_path(file_path)}|{parse_mode}|{delimiter}|{json_field}|{encoding}"
        scope_key = stable_scope("text_file", unique_id or "", source_key)
        cursor = IteratorStateStore.peek_cursor(scope_key)
        return hash((scope_key, fingerprint, cursor, reset, loop_mode, enable_log))

    def run(
        self,
        file_path,
        parse_mode,
        delimiter,
        json_field,
        encoding,
        loop_mode,
        reset,
        enable_log=False,
        unique_id=None,
    ):
        """按游标输出下一条文件文本及来源位置。"""
        _log_params(
            enable_log,
            "TextFile",
            "inputs",
            {
                "file_path": file_path,
                "parse_mode": parse_mode,
                "delimiter": delimiter,
                "json_field": json_field,
                "encoding": encoding,
                "loop_mode": loop_mode,
                "reset": reset,
                "unique_id": unique_id,
            },
        )
        items = _load_text_items_from_file(
            file_path=file_path,
            parse_mode=parse_mode,
            delimiter=delimiter,
            json_field=json_field,
            encoding=encoding,
        )
        if not items:
            raise ValueError("No text items found in file with current parse settings.")
        _node_log(
            enable_log,
            "[TextFile] parsed=%s mode=%s loop_mode=%s reset=%s file=%s",
            len(items),
            parse_mode,
            loop_mode,
            reset,
            file_path,
        )

        source_key = f"{_normalize_path(file_path)}|{parse_mode}|{delimiter}|{json_field}|{encoding}"
        scope_key = stable_scope("text_file", unique_id or "", source_key)
        index = IteratorStateStore.claim_index(
            scope_key=scope_key, total=len(items), reset=reset, loop_mode=loop_mode
        )
        item = items[index]
        _node_log(
            enable_log,
            "[TextFile] picked index=%s/%s source=%s",
            index,
            len(items) - 1,
            item.source_path,
        )
        _log_params(
            enable_log,
            "TextFile",
            "outputs",
            {
                "TEXT": item.text,
                "SOURCE_PATH": item.source_path,
                "INDEX": index,
                "TOTAL": len(items),
            },
        )
        return item.text, item.source_path, index, len(items)


NODE_CLASS_MAPPINGS = {
    "IteratorLoadImage": IteratorLoadImage,
    "IteratorLoadVideoPath": IteratorLoadVideoPath,
    "IteratorLoadTextFromDir": IteratorLoadTextFromDir,
    "IteratorLoadTextFromFile": IteratorLoadTextFromFile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "IteratorLoadImage": "Iterator Load Image",
    "IteratorLoadVideoPath": "Iterator Load Video Path",
    "IteratorLoadTextFromDir": "Iterator Load Text From Dir",
    "IteratorLoadTextFromFile": "Iterator Load Text From File",
}
