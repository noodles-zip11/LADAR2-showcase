# Prompt 1 产出：四层施工图

> **DEPRECATED (2026-05-05)**: This document was the initial design output of Prompt 1.
> It proposed a `lidar/` package structure (`lidar/parser`, `lidar/core`, `lidar/input`, `lidar/output`).
> The actual implementation (Prompts 3-8) adopted a flat `can_*.py` structure instead:
> `can_parser.py`, `can_core.py`, `can_input.py`, `can_output.py`, `can_mqtt.py`.
> See [07_module_architecture.md](./07_module_architecture.md) for the current, accurate architecture.
> This document is kept for historical reference only. Do NOT use it as implementation guidance.

本文档是 04_ai_prompt_workflow.md 中 Prompt 1 的执行产出。

**本步没有改动任何代码文件。** 只阅读现有代码并给出重构方案。

---

## 1. 现有代码的四层归类表

当前工程只有一个核心 Python 文件 `can_recv4.py`（1265 行），所有逻辑都集中在其中。以下逐项归类：

### 1.1 输入层 (Input)

| 代码元素 | 行号范围 | 归类说明 |
| --- | --- | --- |
| `open_bus()` | L503-516 | CAN 总线打开，属于 input_can 的核心逻辑 |
| `CsvReplaySource` | L371-500 | CSV 回放数据加载与时间轴索引，属于 input_replay 的核心逻辑 |
| `add_local_venv_to_sys_path()` | L57-67 | 运行环境初始化辅助函数，随入口留在主程序 |
| `PointCloudWindow.poll_live_bus()` | L897-909 | live 模式下从 CAN bus 拉取原始帧并送入 assembler |
| `PointCloudWindow.ingest_live_point()` | L911-927 | 接收 assembler 输出的点，写入 live_points 队列和 CSV |
| `PointCloudWindow.advance_replay()` | L929-956 | replay 模式下推进时间轴游标 |
| `PointCloudWindow.load_replay_source()` | L845-866 | 加载 CSV 文件创建 CsvReplaySource 实例 |
| `PointCloudWindow.choose_replay_csv()` | L835-843 | UI 触发的 CSV 文件选择 |
| `PointCloudWindow.toggle_playback()` | L868-873 | 播放/暂停控制 |
| `PointCloudWindow.on_timeline_pressed/released/changed()` | L875-895 | 时间轴滑块交互 |

注意：当前 `poll_live_bus`、`ingest_live_point`、`advance_replay` 等方法都嵌在 `PointCloudWindow`（UI 类）内部，输入逻辑与 UI 强耦合。重构时需要把它们从 UI 类中剥离出来。

### 1.2 解析层 (Parser)

| 代码元素 | 行号范围 | 归类说明 |
| --- | --- | --- |
| `FRAME_HEADER_ID = 0x123` | L17 | 协议常量：帧头 ID |
| `FRAME_TAIL_ID = 0x124` | L18 | 协议常量：帧尾 ID |
| `REASSEMBLY_TIMEOUT_S = 0.050` | L19 | 协议常量：重组超时 |
| `FORMAL_CSV_FIELDS` | L20-30 | 协议相关的 CSV 字段定义 |
| `LEGACY_CSV_FIELDS` | L31-41 | 兼容旧 CSV 的字段定义 |
| `LidarPoint` (dataclass) | L184-236 | 解析层输出的统一点数据对象，含 `from_measurement` 工厂方法和 `to_csv_row` 序列化 |
| `CanPointAssembler` | L239-347 | **核心：** CAN 双帧重组、字段提取、点对象构造、超时清理、重组统计 |
| `iso_to_unix_us()` | L150-154 | 辅助函数：ISO 时间字符串转 unix 微秒（供 CSV 回放解析用） |
| `parse_int()` / `parse_float()` | L156-168 | 辅助函数：CSV 行解析辅助 |

`CanPointAssembler` 是解析层最核心的类，职责清晰：接收原始 CAN 帧，完成双帧配对（header 0x123 + tail 0x124），输出 `LidarPoint` 对象。当前实现完整且稳定，重构时优先级最高——最先拆出来。

### 1.3 核心处理层 (Core)

| 代码元素 | 行号范围 | 归类说明 |
| --- | --- | --- |
| `compute_xy_mm()` | L80-83 | 极坐标→直角坐标换算 |
| `angular_delta_deg()` | L86-87 | 角度差值计算（处理 360° 回绕） |
| `extract_recent_sweep()` | L90-108 | 从点云中提取最近一圈扫描 |
| `build_sweep_curve()` | L111-129 | 构建扫描轮廓线（含断点 NaN 插入） |
| `STATUS_ESTIMATED` | L50 | 状态位掩码常量 |
| `STATUS_ALERT_MASK` | L51 | 告警掩码常量 |
| `SWEEP_TARGET_DEG` | L52-54 | sweep 提取相关常量 |
| `HISTORY_WINDOW_US` | L46 | 可视化历史窗口常量 |
| `PointCloudWindow.resolve_range_mm()` | L972-985 | 自动量程计算 |
| `PointCloudWindow.visible_points()` | L958-963 | 可见点过滤 |
| `PointCloudWindow.current_status_point()` | L965-970 | 当前点提取 |

这些函数和逻辑负责点云几何换算、扫描提取、量程计算等纯数据处理。它们不直接依赖 UI，但当前部分方法嵌在 `PointCloudWindow` 类中（如 `resolve_range_mm`、`visible_points`），重构时需要剥离。

### 1.4 输出层 (Output)

| 代码元素 | 行号范围 | 归类说明 |
| --- | --- | --- |
| `CsvPointWriter` | L350-368 | CSV 写出（output_csv） |
| `summary_lines_from_stats()` | L171-181 | CSV summary 文本生成（output_csv 辅助） |
| `build_default_csv_path()` | L132-135 | CSV 路径生成（output_csv 辅助） |
| `format_duration_us()` | L138-142 | 时间格式化（output_plot 辅助） |
| `format_distance_mm()` | L145-147 | 距离格式化（output_plot 辅助） |
| `PointCloudWindow._build_ui()` | L575-788 | **UI 构建**（output_plot 的主体） |
| `PointCloudWindow._configure_plot()` | L790-811 | pyqtgraph 配置 |
| `PointCloudWindow.rebuild_guides()` | L987-1042 | 雷达圆环/坐标轴绘制 |
| `PointCloudWindow.render_scene()` | L1044-1111 | **主渲染函数**：散点着色、sweep 曲线、最新点标记 |
| `PointCloudWindow.refresh_status_labels()` | L1113-1169 | 状态面板文本刷新 |
| `PointCloudWindow.update_mode_widgets()` | L817-830 | 模式切换时 UI 更新 |
| `PointCloudWindow.reset_view()` | L813-815 | 视图重置 |
| `PointCloudWindow.shutdown()` | L1171-1196 | 资源释放：关闭 CSV writer、CAN bus |
| `PointCloudWindow.change_replay_speed()` | L832-833 | UI 回调 |
| `PointCloudWindow.closeEvent()` | L1197-1199 | 窗口关闭事件 |

输出层是当前代码中最庞大的部分，其中 `PointCloudWindow` 占据了约 700 行（L519-1199），包含了 UI 构建、点云渲染、状态面板更新、控制面板交互等所有输出逻辑。

### 1.5 入口 / 通用工具

| 代码元素 | 行号范围 | 归类说明 |
| --- | --- | --- |
| `LIVE_POLL_INTERVAL_MS` | L43 | 通用常量 |
| `RENDER_INTERVAL_MS` | L44 | 通用常量 |
| `REPLAY_INTERVAL_MS` | L45 | 通用常量 |
| `DEFAULT_FALLBACK_STEP_US` | L47 | 通用常量 |
| `MIN_AUTO_RANGE_MM` | L48 | 通用常量 |
| `AUTO_RANGE_PADDING` | L49 | 通用常量 |
| `parse_args()` | L1202-1209 | 命令行参数解析 |
| `main()` | L1212-1261 | 程序入口 |

这些元素不属于四层中的任何一层，而是跨层的常量定义和程序入口。

---

## 2. 建议的新文件结构

```
LADAR2/
├── can_recv4.py                  ← 保留为兼容入口，内部改为调用各层模块
│
├── lidar/                        ← 新建 Python 包目录
│   ├── __init__.py
│   │
│   ├── parser/                   ← 解析层
│   │   ├── __init__.py
│   │   ├── protocol.py           ← 协议常量 (FRAME_HEADER_ID, FRAME_TAIL_ID, REASSEMBLY_TIMEOUT_S 等)
│   │   ├── point_model.py        ← LidarPoint 数据类
│   │   └── assembler.py          ← CanPointAssembler 类
│   │
│   ├── core/                     ← 核心处理层
│   │   ├── __init__.py
│   │   ├── geometry.py           ← compute_xy_mm, angular_delta_deg
│   │   ├── sweep.py              ← extract_recent_sweep, build_sweep_curve
│   │   └── constants.py          ← STATUS_ESTIMATED, STATUS_ALERT_MASK, SWEEP_*, HISTORY_WINDOW_US 等
│   │
│   ├── input/                    ← 输入层
│   │   ├── __init__.py
│   │   ├── can_source.py         ← open_bus(), CAN 实时输入逻辑
│   │   ├── csv_replay.py         ← CsvReplaySource 类
│   │   └── helpers.py            ← iso_to_unix_us, parse_int, parse_float, CSV 字段常量
│   │
│   ├── output/                   ← 输出层
│   │   ├── __init__.py
│   │   ├── csv_writer.py         ← CsvPointWriter, summary_lines_from_stats, build_default_csv_path
│   │   ├── plot_window.py        ← PointCloudWindow (UI 主窗口)
│   │   ├── format.py             ← format_duration_us, format_distance_mm (格式化工具)
│   │   └── mqtt_output.py        ← 后续新增，当前仅预留空接口
│   │
│   └── constants.py              ← 跨层共享常量 (poll/render/replay interval, range, padding 等)
│
├── tools/                        ← 现有自检脚本，不动
│   ├── selfcheck_fixtures.py
│   ├── selfcheck_geometry.py
│   ├── selfcheck_protocol.py
│   ├── selfcheck_csv_roundtrip.py
│   ├── selfcheck_contract.py
│   └── selfcheck_luna_firmware.py
│
└── docs/
    └── mqtt_plugin_refactor/     ← 设计文档，不动
        ├── 00_checkpoint3_overview.md
        ├── 01_architecture_and_scope.md
        ├── 02_mqtt_and_broker_notes.md
        ├── 03_topic_interface_and_test.md
        └── 04_ai_prompt_workflow.md
```

### 关键设计说明

1. `can_recv4.py` 保留在原位，作为向后兼容的入口脚本。重构后它的内容将缩减为：导入各层模块 → 调用 `main()`。这保证所有已有的运行命令（`python can_recv4.py --mode live` 等）无需修改。

2. 新模块放在 `lidar/` 包下，按 parser / core / input / output 四层分包。这样做的好处是：目录名本身就是架构文档，后续维护者一眼就能看清结构。

3. `protocol.py` 单独放协议常量。因为 0x123/0x124、CSV 字段名这些常量可能被 parser 和 input 两层同时引用，单独提取可避免循环导入。

4. `mqtt_output.py` 仅预留空接口（如一个 `MqttOutput` 类，所有方法都是 pass），不会在本阶段接入 Paho 或 Broker。

---

## 3. 第一轮重构顺序

建议按以下顺序逐步拆分，每步完成后再做下一步：

### 第 1 步：拆 parser 层（最优先）

原因：parser 层是四个层中边界最清晰、依赖最少的一层。`CanPointAssembler` 已经是一个自包含的类，它只依赖 `time`、`struct`、`LidarPoint`，不依赖 UI、CSV、CAN bus 对象。拆出来风险最低。

具体操作：
- 新建 `lidar/parser/` 包
- 移入 `protocol.py`（常量）、`point_model.py`（LidarPoint）、`assembler.py`（CanPointAssembler）
- `can_recv4.py` 改为 `from lidar.parser.assembler import CanPointAssembler`
- `tools/selfcheck_*.py` 中引用 LidarPoint 的地方改为从新路径导入

### 第 2 步：拆 core 层

原因：core 层的纯函数（`compute_xy_mm`、`angular_delta_deg`、`extract_recent_sweep`、`build_sweep_curve`）不依赖任何状态，可以直接迁移。但 `resolve_range_mm`、`visible_points`、`current_status_point` 目前嵌在 `PointCloudWindow` 方法里，需要先改成独立函数再迁移。

具体操作：
- 新建 `lidar/core/` 包
- 移入 `geometry.py`、`sweep.py`、`constants.py`
- 把 `PointCloudWindow` 中的 `resolve_range_mm` 和 `visible_points` 改为调用 core 层函数
- 保持 `PointCloudWindow` 的行为不变

### 第 3 步：拆 input 层

原因：input 层在当前代码中与 UI 有一定纠缠（`poll_live_bus`、`ingest_live_point`、`advance_replay` 都是 `PointCloudWindow` 的方法）。拆分时需要引入事件/回调机制，把数据流从 UI 对象中解耦。这步的改动面比前两步大，风险略高。

具体操作：
- 新建 `lidar/input/` 包
- 移入 `can_source.py`（`open_bus` 函数）、`csv_replay.py`（`CsvReplaySource` 类）、`helpers.py`（辅助函数）
- `PointCloudWindow` 的 `poll_live_bus` 改为调用 input 层获取数据，再传给 parser 层解析
- `PointCloudWindow` 的 replay 相关方法改为调用 `CsvReplaySource` 的接口

### 第 4 步：拆 output 层（含 UI）

原因：output 层是最大的一块（约 700 行），但也是改动风险最高的一块，因为涉及 PySide6 UI、pyqtgraph 渲染、信号槽连接。放在最后拆是因为前面三步拆完后，output 层只需要消费 parser/core 层的标准化输出，不需要反向修改它们。

具体操作：
- 新建 `lidar/output/` 包
- 移入 `csv_writer.py`、`plot_window.py`、`format.py`
- 新建 `mqtt_output.py`，当前只放空壳类
- `PointCloudWindow` 从 `can_recv4.py` 移到 `plot_window.py`
- `can_recv4.py` 缩减为入口脚本

---

## 4. 每一轮的风险点

### 第 1 步（拆 parser 层）风险点

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| `tools/selfcheck_*.py` 中引用 `LidarPoint`、`CanPointAssembler` 的导入路径变化 | 自检脚本运行失败 | 逐个修改 selfcheck 脚本的 import 路径并运行验证 |
| `LidarPoint.from_measurement` 内部调用 `compute_xy_mm`，如果 `compute_xy_mm` 还留在旧文件中会产生循环导入 | import 报错 | 第 1 步拆 parser 时**同时建 `core/geometry.py`**，只放 `compute_xy_mm` 一个函数。`point_model.py` 从 `lidar.core.geometry` 导入它。不允许在 `point_model.py` 里复制一份实现 |
| `REASSEMBLY_TIMEOUT_S` 被 `CanPointAssembler` 和 `summary_lines_from_stats` 同时使用 | 常量归属不清 | 把它放入 `protocol.py`，让 parser 和 output 都从 parser.protocol 导入 |

**整体风险等级：低。** 这是最安全的一步，因为 parser 层几乎没有外部依赖。

### 第 2 步（拆 core 层）风险点

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| `resolve_range_mm` 内部读取 `self.range_combo.currentText()`（UI 控件状态） | 从 PointCloudWindow 方法变成独立函数时需要传入参数 | 改成纯函数 `resolve_range_mm(range_text, points)` |
| `visible_points` 和 `current_status_point` 内部读取 `self.mode`、`self.live_points`、`self.replay_source` 等 | 与 UI 状态耦合 | 改成纯函数 `visible_points(mode, live_points, replay_source, current_time_us, history_window_us)` |
| 常量 `HISTORY_WINDOW_US` 可能被 core 和 output 同时引用 | 归属问题 | 放入 `core/constants.py`，output 层从 core 导入 |

**整体风险等级：低。** core 层的纯函数不依赖状态，改造后行为等价。主要注意把 UI 耦合的方法改成纯函数。

### 第 3 步（拆 input 层）风险点

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| `poll_live_bus` 内部创建 `CanPointAssembler`（L535）并调用其 `process_message` 和 `prune_stale_frames` | input 与 parser 的生命周期绑定 | 拆分后由主程序（或 controller）负责创建 assembler 并传给 input 层 |
| `ingest_live_point` 同时操作 `live_points` 队列、`csv_writer`、`print` 输出 | 一个方法跨越了 input、output、log 三层 | 拆分后 ingest 只做入队，CSV 写入和 print 移到 output 层或回调 |
| `advance_replay` 内部同时操作 replay 时间轴、timeline_slider、play_pause_button | input 与 UI 耦合 | 拆分后 input 层只推进时间轴，UI 更新通过回调/信号通知 |
| `CsvReplaySource` 内部 `_parse_formal_row` 和 `_parse_legacy_row` 依赖 `compute_xy_mm`、`LidarPoint` | 循环导入 | `CsvReplaySource` 导入 parser 层的 `LidarPoint` 和 core 层的 `compute_xy_mm` |

**整体风险等级：中。** input 层与 UI 和 parser 有较多交互点，需要仔细处理回调和生命周期。建议这步分两个小步：先拆 `CsvReplaySource` 和 `open_bus`，再处理 UI 方法中的 input 逻辑。

### 第 4 步（拆 output 层）风险点

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| `PointCloudWindow` 是 PySide6 QWidget 子类，移动到新文件后可能影响 import 链 | 启动失败 | 确保 `plot_window.py` 正确导入所有依赖 |
| `render_scene` 内部调用了 `self.visible_points()`、`self.current_status_point()` 等，如果这些已经被移到 core 层 | 调用链断裂 | output 层通过参数接收数据，不反向调用 core 层函数 |
| `shutdown` 方法同时关闭 csv_writer、bus、timer | 资源释放 | 保持 shutdown 在 PointCloudWindow 内，但 csv_writer 和 bus 的关闭委托给各自模块 |
| pyqtgraph 和 PySide6 的版本兼容性 | 运行时错误 | 不改任何 pyqtgraph / PySide6 的用法，只做文件移动 |

**整体风险等级：中。** output 层体量最大，但因为它不反向依赖其他层，只要保证 import 正确就不会影响核心逻辑。

---

## 5. 第一轮最小可行改造范围

**目标：** 完成第 1 步（拆 parser 层），让工程从"单文件"变成"多文件"，同时保证所有现有行为完全不变。

### 5.1 本轮只做以下事情

1. 新建目录 `lidar/` 和子包 `lidar/parser/`
2. 从 `can_recv4.py` 中提取以下代码到新文件：
   - `lidar/__init__.py` — 空文件
   - `lidar/parser/__init__.py` — 空文件
   - `lidar/core/__init__.py` — 空文件（第一步先建目录）
   - `lidar/core/geometry.py` — 只放 `compute_xy_mm` 一个函数。避免在多个文件里出现两份实现
   - `lidar/parser/protocol.py` — `FRAME_HEADER_ID`、`FRAME_TAIL_ID`、`REASSEMBLY_TIMEOUT_S`、`FORMAL_CSV_FIELDS`、`LEGACY_CSV_FIELDS`
   - `lidar/parser/point_model.py` — `LidarPoint` 数据类（含 `from_measurement` 和 `to_csv_row`）。`from_measurement` 从 `lidar.core.geometry` 导入 `compute_xy_mm`，不在本文件内复制实现
   - `lidar/parser/assembler.py` — `CanPointAssembler` 类
3. 修改 `can_recv4.py`：
   - 删除已迁移的代码
   - 添加从新模块的导入语句（`from lidar.parser.assembler import CanPointAssembler` 等）
   - 保持 `parse_args()` 和 `main()` 不变
4. 如果 `tools/` 目录下的自检脚本引用了被迁移的类，更新它们的 import 路径

### 5.2 本轮刻意不做的事情

- 不拆 input 层、output 层
- **core 层只放 `compute_xy_mm` 一个函数到 `core/geometry.py`**，不迁移其他 core 逻辑（sweep 提取、统计、告警、状态判断等留在原位）
- 不加入 MQTT 相关的任何代码
- 不修改 UI
- 不修改 CSV 输出格式
- 不修改 CAN 协议
- 不修改 replay 模式
- 不修改 `PointCloudWindow` 类
- 不修改 `CsvPointWriter` 类
- 不修改 `CsvReplaySource` 类（它留在 `can_recv4.py` 中，本轮不动）

### 5.3 必须保持不变的行为清单

| 行为 | 验证方式 |
| --- | --- |
| `python can_recv4.py --mode live --channel can0` 正常启动 | 能打开窗口并显示 CAN 数据 |
| `python can_recv4.py --mode replay --input-csv xxx.csv` 正常启动 | 能打开窗口并回放 CSV |
| CSV 输出字段和格式与改造前完全一致 | diff 改造前后生成的 CSV 文件 |
| 重组统计文本格式不变 | 观察 header 卡片的重组指标 |
| 点云显示效果不变 | 对比改造前后的散点和 sweep 曲线 |
| `tools/selfcheck_*.py` 全部通过 | 运行每个自检脚本 |

### 5.4 验证方式

本轮改造完成后，按以下顺序验证：

1. `python can_recv4.py --mode replay --input-csv <某个CSV>` — 确认窗口正常打开、点云正常显示、时间轴正常工作
2. 如果有 Linux CAN 环境，`python can_recv4.py --mode live` — 确认实时接收正常
3. 运行 `tools/` 下所有自检脚本，确认全部通过
4. 检查 CSV 输出文件，确认格式与改造前一致

---

## 附录：当前代码规模统计

| 区域 | 大致行数 | 占比 |
| --- | --- | --- |
| 常量定义 + 辅助函数 | ~170 行 | 13% |
| `LidarPoint` 数据类 | ~53 行 | 4% |
| `CanPointAssembler`（parser 核心） | ~109 行 | 9% |
| `CsvPointWriter` | ~19 行 | 2% |
| `CsvReplaySource`（input replay） | ~130 行 | 10% |
| `PointCloudWindow`（output UI + 部分耦合逻辑） | ~681 行 | 54% |
| `parse_args` + `main` 入口 | ~60 行 | 5% |
| import + 环境设置 | ~18 行 | 1% |
| 空行 + 分隔 | ~25 行 | 2% |
| **总计** | **~1265 行** | **100%** |

可以看到 `PointCloudWindow` 占了整个文件的一半以上，这也是为什么 output 层放在最后拆——它体量最大、改动面最广，但它同时也是最独立的一层（只消费数据，不产生数据），所以放在最后拆的风险反而可控。
