# LADAR2 Python 代码阅读指南

## 总览

这个项目是一个 2D LiDAR 点云台的 Linux 端程序。它通过 CAN 总线接收 MCU 发来的 0x123/0x124 双帧数据，实时显示点云，同时支持 CSV 录制和回放。最近一次重构把它从单文件 (~1265 行) 拆成了四层架构 + MQTT 输出。

**核心数据流向：**

```
CAN 总线 / CSV 文件  ──→  input 层  ──→  parser 层  ──→  core 层  ──→  output 层
                         (数据采集)      (协议解析)      (业务计算)      (CSV/UI/MQTT)
```

**每个点走过的完整链路：**

```
open_bus() 或 CsvReplaySource        ← input 层：获取原始 CAN 帧或 CSV 行
        ↓
CanPointAssembler.process_message()  ← parser 层：0x123+0x124 双帧配对 → LidarPoint
        ↓
PointCloudWindow.ingest_live_point() ← can_recv4.py：入队 + 写 CSV + 打印
        ↓
extract_recent_sweep()               ← core 层：从队列提取最近一圈扫描
build_sweep_curve()                  ← core 层：构建轮廓线
        ↓
render_scene()                       ← can_recv4.py：pyqtgraph 绘制
refresh_status_labels()              ← can_recv4.py：更新指标 + MQTT 发布
```

---

## 文件一览（建议按此顺序阅读）

### 1. can_parser.py — 解析层（先读这个）

**职责：** CAN 协议定义 + 点数据模型 + 双帧重组。

**核心内容：**

| 符号 | 类型 | 说明 |
| --- | --- | --- |
| `FRAME_HEADER_ID = 0x123` | 常量 | CAN 帧头 ID |
| `FRAME_TAIL_ID = 0x124` | 常量 | CAN 帧尾 ID |
| `REASSEMBLY_TIMEOUT_S = 0.050` | 常量 | 双帧配对超时（秒） |
| `FORMAL_CSV_FIELDS` | 常量 | 9 字段正式 CSV 表头 |
| `compute_xy_mm(d_cm, a_deg)` | 函数 | 极坐标 → 直角坐标 |
| `LidarPoint` | dataclass | **统一点对象**（10 个字段） |
| `CanPointAssembler` | 类 | **双帧重组器** |

**阅读要点：**

- `LidarPoint` 是整个项目唯一的数据载体。理解它的 10 个字段：
  - `host_rx_time_us` — 主机收到 header 帧的 UNIX 微秒时间戳
  - `t_sample_us` — MCU 采样时刻（来自 tail 帧）
  - `angle_tick` / `angle_deg` — 角度（原始 tick / 度数）
  - `distance_cm` — 距离（厘米）
  - `x_mm` / `y_mm` — 直角坐标（由 `compute_xy_mm` 派生）
  - `quality` — 信号质量 0-255
  - `status` — 状态字（bit3=estimated, bit[2:0]=alert_level）
  - `seq` — CAN 帧序号（0-255 循环）
  - `timeline_us` — 回放时间轴（仅 replay 模式使用）

- `CanPointAssembler` 核心方法：
  - `process_message(msg)` — 每收到一条 CAN 帧调用，配对成功返回 `[LidarPoint]`，否则返回 `[]`
  - `prune_stale_frames()` — 定期调用，清理超时未配对的半帧
  - `stats_snapshot()` — 返回 `{ok, timeout, overwrite_a, overwrite_b, pending}`

**依赖：** 无（不 import 项目内其他模块）。

---

### 2. can_input.py — 输入层

**职责：** 数据源抽象——CAN 实时接收和 CSV 回放。

**核心内容：**

| 符号 | 类型 | 说明 |
| --- | --- | --- |
| `open_bus(channel)` | 函数 | 打开 socketcan 总线，返回 `can.Bus` |
| `CsvReplaySource` | 类 | CSV 回放数据源 |
| `iso_to_unix_us(str)` | 函数 | ISO 8601 时间 → UNIX 微秒 |
| `parse_int(str, default)` | 函数 | 安全整数解析 |
| `parse_float(str, default)` | 函数 | 安全浮点解析 |

**阅读要点：**

- `open_bus` 内部惰性 import `can`（因为 `can_input` 模块在 venv 就绪前就会被导入）
- `CsvReplaySource` 是 replay 模式的核心数据源：
  - `__init__` 自动加载 CSV 并构建时间轴
  - 支持两种 CSV 格式自动识别（formal: 有 `host_rx_time_us` 列；legacy: 有 `host_time` 列）
  - `visible_points(time_us, window_us)` — 时间窗口内点查询（bisect 二分）
  - `latest_point(time_us)` — 最近点查询
- 模块底部以注释形式预留了 `SerialCanSource` 接口（串口输入尚未实现）

**依赖：** `can_parser`（需要 `LidarPoint` 和 `compute_xy_mm`）。

---

### 3. can_core.py — 核心处理层

**职责：** 纯数据处理——角度计算、sweep 提取、状态位解析。

**核心内容：**

| 符号 | 类型 | 说明 |
| --- | --- | --- |
| `STATUS_ESTIMATED = 0x08` | 常量 | 状态字 bit3 掩码 |
| `STATUS_ALERT_MASK = 0x07` | 常量 | 告警等级 bit[2:0] 掩码 |
| `SWEEP_TARGET_DEG = 340` | 常量 | sweep 目标角度跨度 |
| `MIN_SWEEP_POINT_COUNT = 24` | 常量 | 最少点数 |
| `SWEEP_BREAK_DISTANCE_MM = 120` | 常量 | 轮廓线断点阈值 |
| `angular_delta_deg(a, b)` | 函数 | 角度差值（处理 360° 回绕） |
| `extract_recent_sweep(pts)` | 函数 | 从点云尾部提取最近 ~340° 扫描 |
| `build_sweep_curve(pts)` | 函数 | 构建轮廓线（含 NaN 断点） |

**阅读要点：**

- `angular_delta_deg(359, 1)` → `-2.0`（顺时针转 2°）。正确处理 360° 回绕。
- `extract_recent_sweep` 从最新点向前回溯，累计角度跨度达到 `SWEEP_TARGET_DEG` 时截断。
- `build_sweep_curve` 相邻点间距超过 `SWEEP_BREAK_DISTANCE_MM` 时插入 `math.nan`，pyqtgraph 的 `connect="finite"` 会在 NaN 处断开线段。
- 模块底部以注释形式预留了 `compute_telemetry()` 和 `check_alarm()` 接口。

**依赖：** 无（只依赖标准库 `math`）。

---

### 4. can_output.py — 输出层（CSV + 格式化）

**职责：** CSV 点云写入、格式化工具。

**核心内容：**

| 符号 | 类型 | 说明 |
| --- | --- | --- |
| `format_duration_us(us)` | 函数 | 微秒 → `MM:SS.s`（时间轴标签） |
| `format_distance_mm(mm)` | 函数 | 毫米 → `x.xx m`（量程环标签） |
| `summary_lines_from_stats(path, s)` | 函数 | 生成 CSV 配套 summary.txt |
| `CsvPointWriter` | 类 | 正式格式 CSV 写入器 |

**阅读要点：**

- `CsvPointWriter` 构造时立即写 `FORMAL_CSV_FIELDS` 表头并 flush
- `write_point()` 每点 flush 一次（保证实时落盘，不怕程序崩溃丢数据）
- `write_summary()` 在程序退出时写入配套 `_summary.txt`
- `build_default_csv_path()` 留在 `can_recv4.py` 因为它依赖 `__file__`
- `PointCloudWindow`（UI）留在 `can_recv4.py`，但它消费本模块的格式化和 CSV 写入功能

**依赖：** `can_parser`（需要 `FORMAL_CSV_FIELDS` 和 `REASSEMBLY_TIMEOUT_S`）。

---

### 5. can_mqtt.py — MQTT 输出层

**职责：** MQTT 发布（status/telemetry/alarm）+ 命令订阅与白名单分发。

**核心内容：**

| 符号 | 类型 | 说明 |
| --- | --- | --- |
| `TOPIC_STATUS` / `TOPIC_TELEMETRY` / `TOPIC_ALARM` / `TOPIC_CMD` | 常量 | 4 个 MQTT topic |
| `ALLOWED_COMMANDS` | 集合 | 白名单 `{"ping", "pause_replay", "resume_replay", "set_replay_speed"}` |
| `CmdDispatcher` | 类 | 命令验证 + 分发 |
| `MqttOutput` | 类 | MQTT 连接与发布 |

**阅读要点：**

- `MqttOutput.connect()` 使用 paho 的 `loop_start()` 在后台线程处理网络 I/O，不阻塞主线程
- 设置了 will 消息：异常断开时 broker 自动发布 `ladar/status` offline
- telemetry 由调用方控制频率（`can_recv4.py` 中节流 1 Hz）
- alarm 仅在告警等级变更时发布
- `CmdDispatcher.dispatch()` 流程：提取 `cmd` 字段 → 白名单验证 → 调用注册的处理器 → 异常捕获
- 非法命令只打日志，不抛异常

**依赖：** paho-mqtt（可选，未安装时 `MqttOutput` 构造抛 `ImportError`）。

---

### 6. can_recv4.py — 主程序入口 + UI

**职责：** 把所有层串起来，提供 PySide6 + pyqtgraph 桌面界面。

**核心内容（按代码顺序）：**

| 区域 | 行号范围（约） | 说明 |
| --- | --- | --- |
| imports | 1-50 | 从四层 + MQTT 导入全部符号 |
| 可视化常量 | 52-58 | `HISTORY_WINDOW_US`, `MIN_AUTO_RANGE_MM` 等 |
| `add_local_venv_to_sys_path()` | 60-70 | venv 路径设置 |
| GUI imports (try/except) | 72-82 | `can`, `pyqtgraph`, `PySide6` |
| `build_default_csv_path()` | 84-90 | 默认 CSV 路径生成 |
| `PointCloudWindow` | 92-870 | **主窗口类**（约 780 行） |
| `parse_args()` | 872-886 | CLI 参数解析 |
| `main()` | 888-970 | 程序入口 |

**`PointCloudWindow` 方法速查：**

| 方法 | 职责 |
| --- | --- |
| `__init__` | 创建 UI 控件、定时器、assembler、MQTT |
| `_build_ui()` | 构造全部 Qt widgets（Header / Radar / Control / Timeline） |
| `_configure_plot()` | 配置 pyqtgraph 散点 + 曲线 + 雷达环 |
| `poll_live_bus()` | live 模式：轮询 CAN bus → assembler → ingest |
| `ingest_live_point()` | 入队 + 写 CSV + 打印 + 修剪旧点 |
| `advance_replay()` | replay 模式：推进时间轴游标 |
| `load_replay_source()` | 加载 CSV 文件并切换到 replay 模式 |
| `visible_points()` | 返回当前时间窗内的点（live: deque 过滤, replay: bisect 查询） |
| `current_status_point()` | 返回最新点 |
| `render_scene()` | **主渲染：** 散点着色 + sweep 曲线 + 最新点标记 + 雷达环 |
| `refresh_status_labels()` | 更新 Header 指标 (MQTT/告警) + 状态面板 + MQTT 发布 |
| `rebuild_guides()` | 绘制雷达圆环和坐标轴标签 |
| `resolve_range_mm()` | 自动量程计算 |
| `shutdown()` | 资源释放：停止定时器、写 CSV summary、关闭 bus、断开 MQTT |

**CLI 参数：**

```
--mode live|replay    数据源模式
--channel can0        CAN 接口名
--input-csv PATH      回放 CSV 文件
--save-csv PATH       录制 CSV 文件
--replay-speed 0.5|1|2  回放速度
--mqtt-host HOST      MQTT broker 地址
--mqtt-port PORT      MQTT broker 端口
--no-mqtt             禁用 MQTT
```

---

### 7. mqtt_smoke_test.py — MQTT 独立烟雾测试

**职责：** 不依赖主程序的独立 MQTT 最小闭环测试。

**运行方式：**

```bash
# 先启动 Mosquitto
sudo systemctl start mosquitto

# 运行测试
python mqtt_smoke_test.py

# 另开终端发送命令
mosquitto_pub -t 'ladar/cmd' -m '{"cmd":"ping"}' -q 1
```

**验证内容：** connect → publish status online → publish telemetry → subscribe cmd → 收到 cmd 打印回调 → Ctrl+C → publish status offline。

---

### 8. tools/selfcheck_*.py — 自检脚本

| 脚本 | 验证内容 |
| --- | --- |
| `selfcheck_protocol.py` | CanPointAssembler 双帧配对（7 项：顺序、乱序、序号回绕、超时、覆写 header、覆写 tail、非法帧） |
| `selfcheck_geometry.py` | angular_delta_deg（6 项）+ extract_recent_sweep（4 项）+ build_sweep_curve（5 项） |
| `selfcheck_csv_roundtrip.py` | CsvPointWriter 写入 → CsvReplaySource 回放 完整往返 |
| `selfcheck_fixtures.py` | 真实 candump 日志重放 + 正式 CSV 数据完整性 |
| `selfcheck_contract.py` | 协议常量契约（0x123/0x124/CSV 字段名）+ selfcheck 脚本副作用守卫 |
| `selfcheck_luna_firmware.py` | TF-Luna 固件编译测试（不涉及 Python 层） |

所有自检脚本通过 `importlib.import_module("can_recv4")` 访问所有符号（因为 `can_recv4` 重新导出了四层的全部内容），不直接 import 子模块。

---

## 关键概念

**CAN 双帧协议：**

MCU 每发一个采样点，拆成两个 CAN 帧：
- Header 帧 (0x123): `[seq, distance_cm_H, distance_cm_L, angle_deg(4B float), quality]`
- Tail 帧 (0x124): `[seq, t_sample_us(4B), angle_tick(2B), status]`

两帧按 `seq` 配对。可能乱序到达（tail 先于 header 收到），`CanPointAssembler` 处理这种情况。

**状态字 (status) 解析：**

```
bit 7: estimated (0x08)  — 1=插值/估算点
bit 3-6: reserved
bit 0-2: alert_level (0x07) — 0=正常, 1-7=告警等级
```

UI 渲染时 `STATUS_ALERT_MASK` 用于告警点橙红高亮，MQTT 发布时用于 alarm topic。

**双模式设计：**

live 和 replay 共用同一套 UI 渲染管线。区别仅在于数据来源：
- live: `poll_live_bus()` → `CanPointAssembler` → `live_points` deque
- replay: `advance_replay()` → `CsvReplaySource.visible_points()` → bisect 二分查询

`visible_points()` 和 `current_status_point()` 两个方法做了模式分发，`render_scene()` 对两种模式透明。

**MQTT 集成点：**

- `main()` 中创建 `MqttOutput`，连接失败不阻止程序启动
- `refresh_status_labels()` 中 1 Hz 节流发布 telemetry，告警变更时发布 alarm
- `shutdown()` 中断开 MQTT（发布 offline）
- 命令通过 `CmdDispatcher` 白名单验证后分发到闭包处理器

---

## 建议阅读顺序

1. **can_parser.py** — 理解数据模型（LidarPoint）和协议（CanPointAssembler）
2. **can_core.py** — 理解业务计算（sweep 提取和状态解析）
3. **can_input.py** — 理解数据来源（live CAN 和 CSV replay）
4. **can_output.py** — 理解数据输出（CSV 写入和格式化）
5. **can_mqtt.py** — 理解 MQTT 输出和命令系统
6. **can_recv4.py** — 理解主程序如何把上面五层串起来
   - 建议从 `main()` 入口开始，然后追踪 `PointCloudWindow.__init__` → `render_scene` → `shutdown`
7. **mqtt_smoke_test.py** — MQTT 独立测试（可选）
