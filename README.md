# ComfyUI-Simple-Iterator

ComfyUI custom nodes for one-sample-per-run batch iteration.

## Common Semantics

- `loop_mode`
  - `loop`: 到末尾后回到第一个继续。
  - `stop`: 到末尾后下一次执行报错停止，避免重复处理。
  - `hold_last`: 到末尾后持续返回最后一个样本。
- `reset`
  - 沿触发复位（edge trigger），仅在 `False -> True` 时复位一次。
  - 例如 `Batch Count = 10` 时，如果 `reset` 全程保持 `True`，只会在第一轮复位。
- `load_always`（仅图片/视频节点）
  - `False`: 允许缓存判定，未变化时可复用结果。
  - `True`: 强制每次都执行节点，绕过缓存判定。
  - “每次”按节点执行次数计算；通常 `Batch Count = 10` 会触发 10 次执行。

## Nodes

### Iterator Load Image

Supports: `.jpg/.jpeg/.png/.webp/.bmp/.tif/.tiff`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | 图片目录路径。 |
| `pattern` | `STRING` | `"*.png,*.jpg,*.jpeg,*.webp"` | 通配符过滤，支持 `,`/`;` 分隔多个模式。 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录。 |
| `order` | `ENUM` | `name_asc` | 排序方式：`name_asc/name_desc/mtime_asc/mtime_desc`。 |
| `loop_mode` | `ENUM` | `stop` | 耗尽策略：`loop/stop/hold_last`。 |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号，仅 `False->True` 生效一次。 |
| `load_always` | `BOOLEAN` | `False` | 是否每次都强制执行节点。 |
| `filename_with_ext` | `BOOLEAN` | `True` | `FILE_NAME` 是否带后缀。 |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `IMAGE` | `IMAGE` | 当前图片张量（RGB）。 |
| `MASK` | `MASK` | 当前图片掩码（无 alpha 时全 0）。 |
| `FILE_PATH` | `STRING` | 当前图片完整路径。 |
| `FILE_NAME` | `STRING` | 当前图片文件名（受 `filename_with_ext` 控制）。 |
| `INDEX` | `INT` | 当前索引（从 0 开始）。 |
| `TOTAL` | `INT` | 样本总数。 |

### Iterator Load Video Path

Supports: `.mp4/.mov/.mkv/.avi/.webm/.m4v/.mpg/.mpeg/.wmv/.flv`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | 视频目录路径。 |
| `pattern` | `STRING` | `"*.mp4"` | 通配符过滤，支持 `,`/`;` 分隔多个模式。 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录。 |
| `order` | `ENUM` | `name_asc` | 排序方式：`name_asc/name_desc/mtime_asc/mtime_desc`。 |
| `loop_mode` | `ENUM` | `stop` | 耗尽策略：`loop/stop/hold_last`。 |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号，仅 `False->True` 生效一次。 |
| `load_always` | `BOOLEAN` | `False` | 是否每次都强制执行节点。 |
| `filename_with_ext` | `BOOLEAN` | `True` | `FILE_NAME` 是否带后缀。 |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `VIDEO_PATH` | `STRING` | 当前视频完整路径。 |
| `FILE_NAME` | `STRING` | 当前视频文件名（受 `filename_with_ext` 控制）。 |
| `INDEX` | `INT` | 当前索引（从 0 开始）。 |
| `TOTAL` | `INT` | 样本总数。 |

### Iterator Load Text From Dir

Directory mode: 每个文本文件整体作为一个输出项。  
Supports: `.txt/.md/.prompt/.json/.jsonl`

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `directory` | `STRING` | `""` | 文本目录路径。 |
| `pattern` | `STRING` | `"*.txt,*.md,*.prompt,*.json,*.jsonl"` | 通配符过滤，支持 `,`/`;` 分隔多个模式。 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录。 |
| `order` | `ENUM` | `name_asc` | 排序方式：`name_asc/name_desc/mtime_asc/mtime_desc`。 |
| `encoding` | `STRING` | `"utf-8"` | 文本读取编码。 |
| `loop_mode` | `ENUM` | `stop` | 耗尽策略：`loop/stop/hold_last`。 |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号，仅 `False->True` 生效一次。 |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `TEXT` | `STRING` | 当前文本文件内容。 |
| `SOURCE_PATH` | `STRING` | 当前文本文件完整路径。 |
| `INDEX` | `INT` | 当前索引（从 0 开始）。 |
| `TOTAL` | `INT` | 样本总数。 |

### Iterator Load Text From File

File mode: 从单文件切分或解析多条文本。

#### Inputs

| Name | Type | Default | Meaning |
|---|---|---|---|
| `file_path` | `STRING` | `""` | 文本文件路径。 |
| `parse_mode` | `ENUM` | `file_split` | 解析方式：`file_split/json_array/jsonl`。 |
| `delimiter` | `STRING` | `"\\n---\\n"` | `file_split` 分隔符，支持转义字符。 |
| `json_field` | `STRING` | `""` | `json_array/jsonl` 对象项提取字段，支持点路径。 |
| `encoding` | `STRING` | `"utf-8"` | 文本读取编码。 |
| `loop_mode` | `ENUM` | `stop` | 耗尽策略：`loop/stop/hold_last`。 |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号，仅 `False->True` 生效一次。 |

#### Outputs

| Name | Type | Meaning |
|---|---|---|
| `TEXT` | `STRING` | 当前文本片段或记录内容。 |
| `SOURCE_PATH` | `STRING` | 来源位置（`#分片索引` 或 `:行号`）。 |
| `INDEX` | `INT` | 当前索引（从 0 开始）。 |
| `TOTAL` | `INT` | 样本总数。 |

## Cursor State

Cursor state is persisted in `.iterator_state.json`.

Scope is isolated by node unique id + source settings, so different nodes do not share the same cursor.
