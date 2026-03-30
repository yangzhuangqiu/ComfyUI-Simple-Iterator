# ComfyUI-Simple-Iterator

ComfyUI custom nodes for one-sample-per-run iteration across image, video, and text sources.

Language: **English** | [简体中文](./README.zh-CN.md)

## Features

- Persistent iterator cursor state (`.iterator_state.json`)
- Scope isolation by node id + source settings
- Edge-triggered reset (`False -> True`)
- Safe stop mode to prevent silent duplicate processing
- File name output with or without extension

## Common Semantics

- `loop_mode`
  - `loop`: wrap to the first item after the last item
  - `stop`: raise an error when exhausted (recommended for batch jobs)
  - `hold_last`: keep returning the last item after exhaustion
- `reset`
  - Edge-triggered reset only
  - Reset happens only when `reset` changes from `False` to `True`
- `load_always` (image/video nodes)
  - `False`: allow normal cache checks
  - `True`: force node execution each run
- `enable_log` (all nodes)
  - `False`: no runtime log output
  - `True`: print node runtime traces to ComfyUI console

## Nodes

### Iterator Load Image

Supports: `.jpg/.jpeg/.png/.webp/.bmp/.tif/.tiff`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | Image directory path. |
| `pattern` | `STRING` | `"*.png,*.jpg,*.jpeg,*.webp"` | Glob patterns, supports comma/semicolon separated values. |
| `recursive` | `BOOLEAN` | `False` | Recursively scan subdirectories. |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc`. |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last`. |
| `reset` | `BOOLEAN` | `False` | Edge-triggered reset signal. |
| `load_always` | `BOOLEAN` | `False` | Force execution every run. |
| `enable_log` | `BOOLEAN` | `False` | Print iterator debug logs for this node run. |
| `filename_with_ext` | `BOOLEAN` | `True` | Whether `FILE_NAME` includes extension. |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `IMAGE` | `IMAGE` | Current image tensor (RGB). |
| `MASK` | `MASK` | Current mask tensor (all zeros if no alpha channel). |
| `FILE_PATH` | `STRING` | Full path of current image. |
| `FILE_NAME` | `STRING` | File name with or without extension. |
| `INDEX` | `INT` | Current index (0-based). |
| `TOTAL` | `INT` | Total available items. |

### Iterator Load Video Path

Supports: `.mp4/.mov/.mkv/.avi/.webm/.m4v/.mpg/.mpeg/.wmv/.flv`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | Video directory path. |
| `pattern` | `STRING` | `"*.mp4"` | Glob patterns, supports comma/semicolon separated values. |
| `recursive` | `BOOLEAN` | `False` | Recursively scan subdirectories. |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc`. |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last`. |
| `reset` | `BOOLEAN` | `False` | Edge-triggered reset signal. |
| `load_always` | `BOOLEAN` | `False` | Force execution every run. |
| `enable_log` | `BOOLEAN` | `False` | Print iterator debug logs for this node run. |
| `filename_with_ext` | `BOOLEAN` | `True` | Whether `FILE_NAME` includes extension. |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `VIDEO_PATH` | `STRING` | Full path of current video. |
| `FILE_NAME` | `STRING` | File name with or without extension. |
| `INDEX` | `INT` | Current index (0-based). |
| `TOTAL` | `INT` | Total available items. |

### Iterator Load Text From Dir

Each text file is emitted as one output item.  
Supports: `.txt/.md/.prompt/.json/.jsonl`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | Text directory path. |
| `pattern` | `STRING` | `"*.txt,*.md,*.prompt,*.json,*.jsonl"` | Glob patterns, supports comma/semicolon separated values. |
| `recursive` | `BOOLEAN` | `False` | Recursively scan subdirectories. |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc`. |
| `encoding` | `STRING` | `"utf-8"` | File encoding. |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last`. |
| `reset` | `BOOLEAN` | `False` | Edge-triggered reset signal. |
| `enable_log` | `BOOLEAN` | `False` | Print iterator debug logs for this node run. |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `TEXT` | `STRING` | Full text content of current file. |
| `SOURCE_PATH` | `STRING` | Full path of current file. |
| `INDEX` | `INT` | Current index (0-based). |
| `TOTAL` | `INT` | Total available items. |

### Iterator Load Text From File

Loads multiple text items from a single file.

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `file_path` | `STRING` | `""` | Input file path. |
| `parse_mode` | `ENUM` | `file_split` | `file_split/json_array/jsonl`. |
| `delimiter` | `STRING` | `"\\n---\\n"` | Delimiter for `file_split` mode (supports escaped characters). |
| `json_field` | `STRING` | `""` | Field path for object entries (dot path supported). |
| `encoding` | `STRING` | `"utf-8"` | File encoding. |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last`. |
| `reset` | `BOOLEAN` | `False` | Edge-triggered reset signal. |
| `enable_log` | `BOOLEAN` | `False` | Print iterator debug logs for this node run. |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `TEXT` | `STRING` | Current text segment or record. |
| `SOURCE_PATH` | `STRING` | Source marker (`#segment` or `:line`). |
| `INDEX` | `INT` | Current index (0-based). |
| `TOTAL` | `INT` | Total available items. |

## Minimal Workflow Examples

1. Image batch processing
   - `Iterator Load Image` -> existing image workflow head node
2. Video batch processing
   - `Iterator Load Video Path` -> your video path-based loader node
3. Prompt/text batch processing
   - `Iterator Load Text From Dir` or `Iterator Load Text From File` -> prompt input branch

## Installation

1. Clone this repo into your ComfyUI `custom_nodes` directory.
2. Install runtime dependencies in the same Python environment used by ComfyUI:

```bash
python -m pip install -r requirements.txt
```

3. Restart ComfyUI.

Notes:
- `torch` is expected to be provided by your ComfyUI environment.
- Keep your `torch` version aligned with your ComfyUI setup.

## Testing

Core layer tests (no ComfyUI runtime dependency):

```bash
python -m pip install pytest
python -m pytest tests/core -m core -q
```

Runtime layer tests (optional, requires `torch`/ComfyUI runtime):

```bash
RUN_RUNTIME_TESTS=1 python -m pytest tests/runtime -m runtime -q
```

Release quality gate (version + lint + core tests):

```bash
python -m pip install pytest ruff
python scripts/release_gate.py
```

## State File

- Cursor state is stored in `.iterator_state.json`
- The file is ignored by git
- State entries are auto-pruned to avoid unbounded growth:
  - TTL cleanup: remove entries not updated for 30 days
  - Capacity cleanup: keep at most 2000 most recently updated entries
- GC settings are configurable with priority:
  - Environment variables (highest)
  - `iterator_config.json`
  - Built-in defaults (lowest)

### GC Config

Create `iterator_config.json` in the plugin root, for example:

```json
{
  "state_ttl_seconds": 2592000,
  "state_max_entries": 2000
}
```

Environment variable override keys:
- `SIMPLE_ITERATOR_STATE_TTL_SECONDS` (`>= 0`, `0` means disable TTL cleanup)
- `SIMPLE_ITERATOR_STATE_MAX_ENTRIES` (`>= 1`)

Tracked example file:
- `iterator_config.example.json` (copy to `iterator_config.json` for local overrides)

## Logging

- Set `enable_log=True` on a node when you want runtime traces.
- Logs are printed to the ComfyUI console with prefix `[SimpleIterator]`.
- Any parameter value longer than 64 characters is truncated automatically.
