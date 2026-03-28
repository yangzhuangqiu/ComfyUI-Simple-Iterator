# ComfyUI-Simple-Iterator

用于图片、视频、文本“每次运行只输出一个样本”的 ComfyUI 自定义节点集。

语言： [English](./README.md) | **简体中文**

## 功能特性

- 持久化游标状态（`.iterator_state.json`）
- 按节点 id + 数据源配置隔离状态
- `reset` 沿触发复位（`False -> True`）
- `stop` 模式防止批处理中静默重复
- 支持输出带后缀或不带后缀的文件名

## 通用语义

- `loop_mode`
  - `loop`：到末尾后回到第一项
  - `stop`：到末尾后下一次执行报错停止（批处理推荐）
  - `hold_last`：到末尾后持续返回最后一项
- `reset`
  - 仅沿触发复位
  - 只有从 `False` 变为 `True` 时才复位
- `load_always`（图片/视频节点）
  - `False`：按正常缓存判定
  - `True`：每次都强制执行
- `enable_log`（所有节点）
  - `False`：不输出运行日志
  - `True`：在 ComfyUI 控制台输出运行日志

## 节点说明

### Iterator Load Image

支持后缀：`.jpg/.jpeg/.png/.webp/.bmp/.tif/.tiff`

#### 输入参数

| 名称 | 类型 | 默认值 | 含义 |
|---|---|---|---|
| `directory` | `STRING` | `""` | 图片目录路径 |
| `pattern` | `STRING` | `"*.png,*.jpg,*.jpeg,*.webp"` | 文件匹配模式，支持逗号/分号分隔 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录 |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc` |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last` |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号 |
| `load_always` | `BOOLEAN` | `False` | 是否每次强制执行 |
| `enable_log` | `BOOLEAN` | `False` | 是否输出本次运行日志 |
| `filename_with_ext` | `BOOLEAN` | `True` | `FILE_NAME` 是否带后缀 |

#### 输出参数

| 名称 | 类型 | 含义 |
|---|---|---|
| `IMAGE` | `IMAGE` | 当前图片张量（RGB） |
| `MASK` | `MASK` | 当前掩码（无 alpha 时全 0） |
| `FILE_PATH` | `STRING` | 当前图片完整路径 |
| `FILE_NAME` | `STRING` | 当前文件名（可带后缀） |
| `INDEX` | `INT` | 当前索引（0 开始） |
| `TOTAL` | `INT` | 样本总数 |

### Iterator Load Video Path

支持后缀：`.mp4/.mov/.mkv/.avi/.webm/.m4v/.mpg/.mpeg/.wmv/.flv`

#### 输入参数

| 名称 | 类型 | 默认值 | 含义 |
|---|---|---|---|
| `directory` | `STRING` | `""` | 视频目录路径 |
| `pattern` | `STRING` | `"*.mp4"` | 文件匹配模式，支持逗号/分号分隔 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录 |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc` |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last` |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号 |
| `load_always` | `BOOLEAN` | `False` | 是否每次强制执行 |
| `enable_log` | `BOOLEAN` | `False` | 是否输出本次运行日志 |
| `filename_with_ext` | `BOOLEAN` | `True` | `FILE_NAME` 是否带后缀 |

#### 输出参数

| 名称 | 类型 | 含义 |
|---|---|---|
| `VIDEO_PATH` | `STRING` | 当前视频完整路径 |
| `FILE_NAME` | `STRING` | 当前文件名（可带后缀） |
| `INDEX` | `INT` | 当前索引（0 开始） |
| `TOTAL` | `INT` | 样本总数 |

### Iterator Load Text From Dir

目录模式：每个文本文件整体作为一条输出。  
支持后缀：`.txt/.md/.prompt/.json/.jsonl`

#### 输入参数

| 名称 | 类型 | 默认值 | 含义 |
|---|---|---|---|
| `directory` | `STRING` | `""` | 文本目录路径 |
| `pattern` | `STRING` | `"*.txt,*.md,*.prompt,*.json,*.jsonl"` | 文件匹配模式，支持逗号/分号分隔 |
| `recursive` | `BOOLEAN` | `False` | 是否递归扫描子目录 |
| `order` | `ENUM` | `name_asc` | `name_asc/name_desc/mtime_asc/mtime_desc` |
| `encoding` | `STRING` | `"utf-8"` | 文件编码 |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last` |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号 |
| `enable_log` | `BOOLEAN` | `False` | 是否输出本次运行日志 |

#### 输出参数

| 名称 | 类型 | 含义 |
|---|---|---|
| `TEXT` | `STRING` | 当前文本内容（整文件） |
| `SOURCE_PATH` | `STRING` | 当前文件完整路径 |
| `INDEX` | `INT` | 当前索引（0 开始） |
| `TOTAL` | `INT` | 样本总数 |

### Iterator Load Text From File

单文件模式：从一个文件中拆分/解析出多条文本。

#### 输入参数

| 名称 | 类型 | 默认值 | 含义 |
|---|---|---|---|
| `file_path` | `STRING` | `""` | 输入文件路径 |
| `parse_mode` | `ENUM` | `file_split` | `file_split/json_array/jsonl` |
| `delimiter` | `STRING` | `"\\n---\\n"` | `file_split` 分隔符（支持转义） |
| `json_field` | `STRING` | `""` | 对象记录取值字段（支持点路径） |
| `encoding` | `STRING` | `"utf-8"` | 文件编码 |
| `loop_mode` | `ENUM` | `stop` | `loop/stop/hold_last` |
| `reset` | `BOOLEAN` | `False` | 沿触发复位信号 |
| `enable_log` | `BOOLEAN` | `False` | 是否输出本次运行日志 |

#### 输出参数

| 名称 | 类型 | 含义 |
|---|---|---|
| `TEXT` | `STRING` | 当前文本片段/记录 |
| `SOURCE_PATH` | `STRING` | 来源标记（`#分片` 或 `:行号`） |
| `INDEX` | `INT` | 当前索引（0 开始） |
| `TOTAL` | `INT` | 样本总数 |

## 最小工作流示例

1. 图片批处理  
   `Iterator Load Image` -> 现有图片工作流入口
2. 视频批处理  
   `Iterator Load Video Path` -> 你的视频路径加载节点
3. 文本批处理  
   `Iterator Load Text From Dir` 或 `Iterator Load Text From File` -> prompt 分支

## 安装

1. 将本仓库克隆到 ComfyUI 的 `custom_nodes` 目录。
2. 在与 ComfyUI 相同的 Python 环境中安装运行依赖：

```bash
python -m pip install -r requirements.txt
```

3. 重启 ComfyUI。

说明：
- `torch` 默认由 ComfyUI 运行环境提供。
- 请保持 `torch` 与你的 ComfyUI 环境版本一致。

## 测试

```bash
python -m pip install pytest
python -m pytest
```

## 状态文件

- 游标状态保存在 `.iterator_state.json`
- 该文件已加入 git ignore

## 日志

- 将任一节点的 `enable_log` 设为 `True`，即可输出该节点运行日志。
- 日志会打印到 ComfyUI 控制台，前缀为 `[SimpleIterator]`。
- 任意参数值超过 64 个字符时会自动截断。
