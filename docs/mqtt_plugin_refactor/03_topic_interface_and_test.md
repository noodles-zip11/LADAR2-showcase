# Topic 接口与测试计划

本文档是后续编码的合同文档。所有 MQTT 相关的 topic、payload、字段语义、命令边界和测试验收项都以本文档为准。

本阶段约束：不改 MCU、不改 CAN 协议、不引入 ESP32、不接云平台。Python 端按四层重构分步推进，本文件作为 MQTT 扩展阶段的接口合同。

---

## 5. Topic 设计与消息模型

### 5.1 统一点对象字段

以下字段来自当前 `can_recv4.py` 中 `LidarPoint` 数据类和 CAN 双帧协议，是整个系统的正式字段。MQTT 模块只消费这些字段，不发明新字段，不重命名字段。

#### 5.1.1 协议原始字段

| 字段名 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- |
| `host_rx_time_us` | `int` | `CanPointAssembler._try_commit_frame()` 中 `time.time_ns() // 1000` | Linux 完成点对象重组（双帧配对成功）时记录的主机时间，单位微秒。**不是**原始 CAN 帧接收入口的时间 |
| `t_sample_us` | `int` | CAN 尾帧 `0x124` bytes[1:5] | MCU 采样时间戳，单位微秒 |
| `angle_tick` | `int` | CAN 尾帧 `0x124` bytes[5:7] | MCU 角度编码器原始值 |
| `angle_deg` | `float` | CAN 头帧 `0x123` bytes[3:7] (big-endian float) | 角度，单位度 |
| `distance_cm` | `int` | CAN 头帧 `0x123` byte[1]<<8 \| byte[2] (big-endian uint16) | 距离，单位厘米 |
| `quality` | `int` | CAN 头帧 `0x123` byte[7] | 信号质量 |
| `status` | `int` | CAN 尾帧 `0x124` byte[7] | 状态字节 |

#### 5.1.2 几何派生字段

| 字段名 | 类型 | 计算方式 | 说明 |
| --- | --- | --- | --- |
| `x_mm` | `float` | `distance_cm * 10 * cos(radians(angle_deg))` | X 坐标，单位毫米。注意 Python `math.cos/sin` 接受弧度，必须先将 `angle_deg` 通过 `math.radians()` 转换 |
| `y_mm` | `float` | `distance_cm * 10 * sin(radians(angle_deg))` | Y 坐标，单位毫米。同上，角度必须先转弧度 |

**关键约束：** `distance_cm` 是正式协议字段，不得引入 `distance_mm` 作为字段名。`host_rx_time_us` 和 `t_sample_us` 含义完全不同，不可混淆。

#### 5.1.3 辅助字段

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `seq` | `int` 或 `None` | 帧序号（CAN data[0]）。formal CSV replay 中为 None；legacy CSV replay 中保留原始 seq 值 |
| `timeline_us` | `int` | 回放模式下相对起始时间的偏移量，单位微秒 |

#### 5.1.4 状态字节定义

```text
status byte (8 bit):
  bit[2:0] = STATUS_ALERT_MASK (0x07)  → 告警/异常标志，非零表示异常
  bit[3]    = STATUS_ESTIMATED (0x08)   → 该点为估计值（非直接测量）
  bit[7:4]  = 预留
```

判定规则：

- `status & 0x07 != 0` → 当前点存在告警
- `status & 0x08 != 0` → 当前点为估计值

### 5.2 Topic 设计

#### 5.2.1 Topic 命名规则

```text
lidar/{node_id}/{message_type}
```

- `lidar` — 项目前缀，固定
- `{node_id}` — 节点编号（纯数字），默认 `01`，可通过启动参数 `--node-id` 配置。仅用于 topic 路由，不与 payload 中的 `device_id` 混淆
- `{message_type}` — 消息类型，取值为 `status` / `telemetry` / `alarm` / `cmd`

**关键约定：** topic 中的 `{node_id}` 是短标识（如 `01`），payload 中的 `device_id` 是长标识（如 `lidar-01`）。两者语义不同：`node_id` 用于 MQTT topic 层级路由，`device_id` 用于 payload 中的设备身份字符串。实现时配置项 `MQTT_NODE_ID` 对应 topic 路由参数，`MQTT_DEVICE_ID` 对应 payload 内字段值。

#### 5.2.2 Topic 表

| Topic | 方向 | QoS | Retain | 发布频率 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `lidar/01/status` | Linux → Broker | 1 | true | 启动时、模式切换时 | 设备在线状态与运行模式 |
| `lidar/01/telemetry` | Linux → Broker | 0 | false | 周期性，默认每 2 秒 | 点云统计摘要与最近点信息 |
| `lidar/01/alarm` | Linux → Broker | 1 | false | 告警触发时 | 告警事件通知 |
| `lidar/01/cmd` | 外部 → Linux | 1 | false | 外部触发 | 远程命令下发 |

#### 5.2.3 QoS 策略说明

| 消息类型 | QoS | 原因 |
| --- | --- | --- |
| `status` | 1 | 状态变化不高频，希望尽量送达；retain=true 让新订阅者立刻看到当前状态 |
| `telemetry` | 0 | 周期摘要可以丢一两条，下一条会覆盖；降低网络和 Broker 负担 |
| `alarm` | 1 | 告警重要，应该尽量送达 |
| `cmd` | 1 | 命令需要可靠送达；但接收端必须处理可能的重复（幂等） |

### 5.3 Payload 定义与示例

所有 payload 使用 JSON 格式，编码为 UTF-8。

#### 5.3.1 status payload

发布时机：程序启动时发布 online；模式切换时更新；异常断开时由 will 发布 offline。

**online 示例：**

```json
{
  "device_id": "lidar-01",
  "state": "online",
  "mode": "live",
  "version": "1.0.0",
  "ts": 1714521600000
}
```

**offline（will 遗嘱）示例：**

```json
{
  "device_id": "lidar-01",
  "state": "offline"
}
```

**模式切换示例（live → replay）：**

```json
{
  "device_id": "lidar-01",
  "state": "online",
  "mode": "replay",
  "version": "1.0.0",
  "ts": 1714521700000
}
```

字段说明：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `device_id` | `string` | 是 | 设备标识，如 `"lidar-01"` |
| `state` | `string` | 是 | `"online"` 或 `"offline"` |
| `mode` | `string` | online 时必选 | `"live"` 或 `"replay"` |
| `version` | `string` | 否 | 程序版本号，如 `"1.0.0"` |
| `ts` | `long` | online 时必选 | 当前 Unix 时间戳，单位毫秒 |

#### 5.3.2 telemetry payload

发布时机：周期性发布，默认每 2 秒一次。

**live 模式示例：**

```json
{
  "device_id": "lidar-01",
  "mode": "live",
  "ts": 1714521602000,
  "point_count": 347,
  "sweep_point_count": 186,
  "min_distance_cm": 46,
  "min_distance_angle_deg": 127.35,
  "latest_quality": 15,
  "latest_status": 0,
  "reassembly": {
    "ok": 2340,
    "timeout": 3,
    "overwrite_a": 0,
    "overwrite_b": 0,
    "pending": 1
  }
}
```

**replay 模式示例：**

```json
{
  "device_id": "lidar-01",
  "mode": "replay",
  "ts": 1714521602000,
  "point_count": 289,
  "sweep_point_count": 152,
  "min_distance_cm": 38,
  "min_distance_angle_deg": 45.10,
  "latest_quality": 12,
  "latest_status": 0,
  "reassembly": {
    "ok": 1200,
    "timeout": 1,
    "overwrite_a": 0,
    "overwrite_b": 0,
    "pending": 0
  },
  "replay_progress_pct": 67.3
}
```

字段说明：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `device_id` | `string` | 是 | 设备标识 |
| `mode` | `string` | 是 | `"live"` 或 `"replay"` |
| `ts` | `long` | 是 | 当前 Unix 时间戳，单位毫秒 |
| `point_count` | `int` | 是 | 当前可视窗口内的总点数 |
| `sweep_point_count` | `int` | 是 | 最近一圈扫描的点数 |
| `min_distance_cm` | `int` 或 `null` | 是 | 当前窗口内最小距离（厘米），无数据时为 null |
| `min_distance_angle_deg` | `float` 或 `null` | 是 | 最小距离对应的角度，无数据时为 null |
| `latest_quality` | `int` 或 `null` | 是 | 最新点的质量值，无数据时为 null |
| `latest_status` | `int` 或 `null` | 是 | 最新点的状态字节，无数据时为 null |
| `reassembly` | `object` | 是 | 重组统计快照 |
| `reassembly.ok` | `int` | 是 | 成功重组点数 |
| `reassembly.timeout` | `int` | 是 | 超时丢弃帧数 |
| `reassembly.overwrite_a` | `int` | 是 | 头帧覆写次数 |
| `reassembly.overwrite_b` | `int` | 是 | 尾帧覆写次数 |
| `reassembly.pending` | `int` | 是 | 当前待配对帧数 |
| `replay_progress_pct` | `float` | replay 时必选 | 回放进度百分比，0.0~100.0 |

#### 5.3.3 alarm payload

发布时机：由 `alarm_detector` 模块独立跟踪告警状态。告警状态变化时立即发布 alarm，**不依赖** telemetry 的 2 秒周期。短暂告警在 telemetry 间隔内出现又消失时也能被捕获。

告警来源分两类：

- MCU 原生告警：`latest_point.status & 0x07 != 0`，`alarm_source="mcu_status"`。
- Linux/Windows 网关派生告警：由核心层根据最近窗口最小距离、有效点间隙等业务规则派生，`alarm_source="derived_distance"` 或 `alarm_source="derived_no_valid_points"`。

注意：`latest_status=8` 是 `STATUS_ESTIMATED` (`0x08`)，不代表 MCU 原生告警；它可以和派生告警同时出现。

**告警触发示例：**

```json
{
  "device_id": "lidar-01",
  "ts": 1714521605000,
  "alarm": true,
  "alarm_status": 3,
  "alarm_source": "mcu_status",
  "alarm_reason": "status bit[2:0]=0x03",
  "threshold_cm": null,
  "min_distance_cm": 12,
  "alarm_description": "status bit[2:0]=0x03",
  "latest_point": {
    "distance_cm": 12,
    "angle_deg": 89.50,
    "quality": 8,
    "status": 3
  }
}
```

**派生距离告警示例：**

```json
{
  "device_id": "lidar-01",
  "ts": 1778342621757,
  "alarm": true,
  "alarm_status": 2,
  "alarm_source": "derived_distance",
  "alarm_reason": "derived_too_near",
  "threshold_cm": 30,
  "min_distance_cm": 28,
  "alarm_description": "derived_distance: derived_too_near",
  "latest_point": {
    "distance_cm": 28,
    "angle_deg": 124.10,
    "quality": 255,
    "status": 8
  }
}
```

**告警恢复示例：**

```json
{
  "device_id": "lidar-01",
  "ts": 1714521610000,
  "alarm": false,
  "alarm_status": 0,
  "alarm_source": "clear",
  "alarm_reason": "alarm cleared",
  "threshold_cm": null,
  "min_distance_cm": 85,
  "alarm_description": "alarm cleared",
  "latest_point": {
    "distance_cm": 85,
    "angle_deg": 200.30,
    "quality": 15,
    "status": 0
  }
}
```

字段说明：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `device_id` | `string` | 是 | 设备标识 |
| `ts` | `long` | 是 | Unix 时间戳，毫秒 |
| `alarm` | `boolean` | 是 | `true`=告警触发，`false`=告警恢复 |
| `alarm_status` | `int` | 是 | 告警等级。MCU 告警时来自 `status & 0x07`；派生告警中 `1`=near/no-valid-points，`2`=too-near；恢复时为 0 |
| `alarm_source` | `string` | 是 | `mcu_status` / `derived_distance` / `derived_no_valid_points` / `clear` |
| `alarm_reason` | `string` | 是 | `status bit[...]` / `derived_too_near` / `derived_near_obstacle` / `derived_no_valid_points` / `alarm cleared` |
| `threshold_cm` | `int` 或 `null` | 是 | 派生距离告警阈值，例如 30 或 50；非距离告警为 null |
| `min_distance_cm` | `int` 或 `null` | 是 | 告警窗口内最小距离；无有效点告警可为 null |
| `alarm_description` | `string` | 是 | 人类可读的告警描述 |
| `latest_point` | `object` | 是 | 触发/恢复时最新点的关键字段摘要 |
| `latest_point.distance_cm` | `int` | 是 | 距离，厘米 |
| `latest_point.angle_deg` | `float` | 是 | 角度，度 |
| `latest_point.quality` | `int` | 是 | 信号质量 |
| `latest_point.status` | `int` | 是 | 状态字节原始值 |

#### 5.3.4 cmd payload（接收）

外部向 `lidar/01/cmd` 发布的命令消息。

**ping 示例：**

```json
{
  "cmd": "ping",
  "req_id": "a1b2c3"
}
```

**pause_replay 示例：**

```json
{
  "cmd": "pause_replay",
  "req_id": "d4e5f6"
}
```

**resume_replay 示例：**

```json
{
  "cmd": "resume_replay",
  "req_id": "g7h8i9"
}
```

**set_replay_speed 示例：**

```json
{
  "cmd": "set_replay_speed",
  "speed": 2.0,
  "req_id": "j0k1l2"
}
```

字段说明：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `cmd` | `string` | 是 | 命令名称，必须在白名单内 |
| `req_id` | `string` | 否 | 请求标识，用于调试追踪，Linux 端收到后原样打日志 |
| `speed` | `float` | `set_replay_speed` 时必选 | 回放速度倍率，允许值 0.5 / 1.0 / 2.0 |

---

## 6. Linux 侧模块设计

### 6.1 MQTT 模块在分层架构中的位置

MQTT 仅存在于输出层，不反向侵入 parser / core / input。

```text
核心处理层产出
  → point_count, sweep_point_count, min_distance, reassembly stats, alarm state
  → MQTT 输出模块读取摘要结果
  → 发布到 Broker
```

### 6.2 建议模块

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| MQTT 输出插件 | `can_mqtt.py` | 封装 Paho 连接、will、subscribe、publish |
| 遥测构建 | `can_recv4.py` (refresh_status_labels) | 从 core/input 层结果构建 telemetry payload JSON |
| 告警检测 | `can_recv4.py` (_check_and_publish_alarm) | 跟踪告警状态变化，判断是否需要发布 alarm |
| 命令分发 | `cmd_handler.py` | 解析 cmd payload，校验白名单，分发执行 |

### 6.3 模块间数据流

```text
can_recv4.py: refresh_status_labels() 构建 telemetry payload
  → JSON → mqtt_output.publish_telemetry(data)

can_recv4.py: _check_and_publish_alarm(point) 检测告警状态变化
  → JSON → mqtt_output.publish_alarm(data)

can_mqtt.py: CmdDispatcher.dispatch(topic, payload)
  → 验证白名单 → 执行注册的处理器 (ping/pause_replay/resume_replay/set_replay_speed)
```

### 6.4 核心处理层需要暴露的接口

MQTT 输出模块不直接访问 `PointCloudWindow` 内部状态，而是从 core 层或 controller 层获取以下信息：

| 数据项 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- |
| `mode` | `string` | controller | `"live"` 或 `"replay"` |
| `point_count` | `int` | core 层 | 当前可视窗口内的总点数 |
| `sweep_point_count` | `int` | core 层 | 最近一圈扫描点数 |
| `min_distance_cm` | `int` 或 `None` | core 层 | 窗口内最小距离（厘米） |
| `min_distance_angle_deg` | `float` 或 `None` | core 层 | 最小距离对应角度 |
| `latest_point` | `LidarPoint` 或 `None` | core 层 | 最新点数据 |
| `reassembly_stats` | `dict` | parser 层 | 重组统计快照 |
| `replay_progress_pct` | `float` 或 `None` | input 层 | 回放进度百分比 |

### 6.5 异步与阻塞策略

- MQTT 使用 `client.loop_start()` 在后台线程维护网络心跳。
- `publish` 调用使用 `mqtt.Client.publish()` 的异步模式，不在 CAN 接收主循环中阻塞等待 PUBACK。
- 告警和状态发布频率低，不存在性能瓶颈。
- telemetry 周期发布使用独立的 QTimer（默认间隔 2000ms，由 `MQTT_TELEMETRY_INTERVAL_S` 控制）。**不得**接在 render_scene 的 33ms timer 上；如果实现时选择在 render 回调里触发 telemetry，必须在回调内部做 2 秒节流（记录上次发布时间戳并在间隔不足时跳过）。

### 6.6 MQTT 连接配置项

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `MQTT_BROKER_HOST` | `"localhost"` | Broker 地址 |
| `MQTT_BROKER_PORT` | `1883` | Broker 端口 |
| `MQTT_NODE_ID` | `"01"` | 节点编号，用于 topic 路由 `lidar/{node_id}/...` |
| `MQTT_DEVICE_ID` | `"lidar-01"` | 设备标识字符串，用于 payload 内 `device_id` 字段 |
| `MQTT_KEEPALIVE` | `30` | 心跳间隔，秒 |
| `MQTT_TELEMETRY_INTERVAL_S` | `2.0` | telemetry 发布间隔，秒 |
| `MQTT_ENABLED` | `True` | 是否启用 MQTT（方便调试时关闭） |

---

## 7. 命令下发与协议边界

### 7.1 第一版命令白名单

| 命令 | 参数 | 作用 | 适用模式 | 幂等性 |
| --- | --- | --- | --- | --- |
| `ping` | 无 | 回复日志确认 Linux 端 MQTT 命令链路通畅 | live / replay | 是 |
| `pause_replay` | 无 | 暂停回放 | replay | 是（重复暂停无副作用） |
| `resume_replay` | 无 | 继续回放 | replay | 是（重复继续无副作用） |
| `set_replay_speed` | `speed`: 0.5 / 1.0 / 2.0 | 设置回放速度倍率 | replay | 是 |

### 7.2 命令处理规则

1. **白名单校验：** 收到 cmd 后先检查 `cmd` 字段是否在白名单中。不在白名单内的命令，打印警告日志，不执行任何动作。
2. **模式校验：** `pause_replay`、`resume_replay`、`set_replay_speed` 只在 replay 模式下有效。live 模式下收到这些命令，打印警告日志，不执行。
3. **参数校验：** `set_replay_speed` 的 `speed` 参数必须是 0.5 / 1.0 / 2.0 之一。非法值打印警告日志，不执行。
4. **幂等性：** 所有命令必须幂等。重复执行同一命令不产生副作用。
5. **日志记录：** 每条收到的命令（包括非法命令）都要打印日志，格式为 `MQTT cmd: cmd=xxx req_id=yyy result=zzz`。
6. **不回显 payload：** 第一版不在 MQTT 上回复命令执行结果，只通过日志记录。后续版本可增加 `lidar/01/cmd_response` topic。

### 7.3 命令边界

以下行为严格禁止：

- 不通过 MQTT 命令修改 MCU 协议或 CAN 帧结构。
- 不通过 MQTT 命令直接控制硬件（如修改采样率、旋转速度）。
- 不通过 MQTT 命令启动或停止 CAN 接收。
- 不通过 MQTT 上传全量原始点云。
- 不扩展成复杂权限系统或几十个命令。

命令只影响 Linux 侧行为，不改 MCU。

### 7.4 非法命令处理示例

收到未知命令：

```json
{"cmd": "reboot", "req_id": "xxx"}
```

日志输出：

```text
MQTT cmd: cmd=reboot req_id=xxx result=REJECTED unknown_command
```

收到模式不匹配的命令（live 模式下收到 pause_replay）：

```json
{"cmd": "pause_replay", "req_id": "yyy"}
```

日志输出：

```text
MQTT cmd: cmd=pause_replay req_id=yyy result=REJECTED wrong_mode(current=live)
```

收到参数非法的命令：

```json
{"cmd": "set_replay_speed", "speed": 5.0, "req_id": "zzz"}
```

日志输出：

```text
MQTT cmd: cmd=set_replay_speed req_id=zzz result=REJECTED invalid_speed(5.0)
```

---

## 8. 运行流程与时序

### 8.1 程序启动流程

```text
main()
  → 解析命令行参数（确定 mode=live 或 replay）
  → 创建 CAN bus（live）或加载 CSV（replay）
  → 创建 CanPointAssembler（live）
  → 创建 CsvPointWriter（live）
  → 创建 MQTT 客户端
    → 设置 will: lidar/01/status {"state":"offline"} QoS1 retain=true
    → 设置回调: on_connect, on_message, on_disconnect
    → **捕获可能发生的连接异常**，失败时记录日志并置 MQTT 为 disabled 状态，**不阻塞主函数进入 UI**。推荐使用 `connect_async()` 后台连接，或使用短超时的阻塞 `connect()` 并用 try/except 包裹。**不允许**使用默认阻塞 `connect()` 对远端不可达 broker 无限等待
  → 若连接成功 → `loop_start()`
  → on_connect 回调触发（仅连接成功时）
    → subscribe("lidar/01/cmd", QoS=1)
    → 从 args/controller 读取当前实际 mode（而非写死 "live"）
    → publish("lidar/01/status", {"state":"online","mode": actual_mode}, QoS=1, retain=true)
  → 创建 PointCloudWindow（传入实际 mode 和 MQTT disabled 状态）
  → replay 模式下若通过 --input-csv 预加载 CSV，CSV 加载完成后 publish 更新 status
  → 启动 QTimer（poll + render + 独立 telemetry timer）
  → app.exec()
```

**关键要求：** on_connect 回调中 `mode` 字段必须从 `args.mode` 或 controller 当前状态读取，不能写死为 `"live"`。replay 模式下如果 CSV 尚未加载完毕，建议先发布 `mode="replay"`，CSV 加载完成后再发布一次 status（进度更新或确认数据源就绪）。

### 8.2 运行中 MQTT 时序

```text
每 2 秒 telemetry timer 触发
  → telemetry_builder.build() 收集当前状态
  → mqtt_output.publish("lidar/01/telemetry", payload, QoS=0)

新 LiDAR 点进入时（ingest 入口）立即触发 alarm 检测
  → alarm_detector.check(point)      ← **主检查入口，每个点都跑**
  → 内部维护 last_alarm_active 状态，与 telemetry 发布周期无关
  → 若 alarm_active 变化（false→true 或 true→false）:
    → 立即 mqtt_output.publish("lidar/01/alarm", payload, QoS=1)

render_scene 中可选做第二次检查和发布（作为 UI 刷新辅助）
  → 检查 latest_point 状态，与 ingest 路径共用同一份 last_alarm_active

收到 cmd 消息
  → on_message 回调
  → cmd_handler.dispatch(payload)
  → 执行对应 Linux 侧动作
  → 打印日志
```

### 8.3 模式切换时序

```text
用户在 UI 切换到 replay 模式
  → MQTT publish status 更新 mode="replay"

用户在 UI 切换回 live 模式
  → MQTT publish status 更新 mode="live"
```

### 8.4 程序关闭流程

```text
closeEvent / shutdown()
  → MQTT publish("lidar/01/status", {"state":"offline"}, QoS=1, retain=true)
  → 等待 publish 完成（wait_for_publish() 或短超时 1s），确保 offline 消息已送达 Broker
  → MQTT disconnect()
  → MQTT loop_stop()
  → 关闭 CSV writer（live 模式写 summary）
  → 关闭 CAN bus
  → 退出
```

**关键要求：** QoS 1 publish 是异步的。正常关闭时 `publish(offline)` 之后必须调用 `wait_for_publish()` 或轮询等待 PUBACK（建议超时 1 秒），然后才能 `disconnect()`。否则 retained status 可能永久停留在 online。这条写死在实现合同里，不可打折扣。

注意：正常关闭时主动发布 offline，这样 will 遗嘱不会触发。只有异常断开（进程崩溃、断电、杀进程）时 Broker 才会代替发布 will 消息。

### 8.5 MQTT 断线处理

- MQTT 断线不影响 CAN 接收、点云显示、CSV 写入和 replay。
- Paho 的 `loop_start` 会自动尝试重连。
- 重连成功后重新 subscribe cmd topic 并发布 status online。
- 断线期间 telemetry 和 alarm 的 publish 调用会失败但不会抛异常（Paho 内部处理），不会阻塞主循环。

---

## 9. 测试与验收计划

### 9.1 测试环境要求

| 项目 | 要求 |
| --- | --- |
| Broker | 本机安装 Mosquitto，默认端口 1883，暂不启用 TLS 和认证 |
| Python 依赖 | `paho-mqtt` 已安装 |
| CAN 环境 | 测试阶段可不连接真实 CAN 硬件，使用 replay 模式验证 |
| 调试工具 | `mosquitto_sub` 和 `mosquitto_pub` 命令行工具可用 |

### 9.2 验收测试清单

#### 9.2.1 MQTT 连接与状态

| 编号 | 测试项 | 操作 | 预期结果 | 通过标准 |
| --- | --- | --- | --- | --- |
| T01 | 程序启动后 status online | 启动程序，用 `mosquitto_sub -h localhost -t "lidar/01/status" -v` 监听 | 收到 `{"state":"online","mode":"...","version":"1.0.0","ts":...}` | 收到且 retain=true |
| T02 | 新订阅者立刻拿到状态 | 程序运行中，新开一个 `mosquitto_sub` 订阅 status | 立刻收到 retain 的 online 消息 | 不需要等下一次 publish |
| T03 | 正常关闭发布 offline | 正常关闭程序窗口 | `mosquitto_sub` 收到 `{"state":"offline"}` | 收到 |
| T04 | 异常断开触发 will | `kill -9` 杀掉进程 | Broker 代替发布 `{"state":"offline"}` | 收到（可能有几秒延迟取决于 keepalive） |

#### 9.2.2 Telemetry 遥测

| 编号 | 测试项 | 操作 | 预期结果 | 通过标准 |
| --- | --- | --- | --- | --- |
| T05 | live 模式周期 telemetry | live 模式运行，订阅 telemetry topic | 每 2 秒收到一条 telemetry 消息 | 间隔约 2 秒 |
| T06 | replay 模式 telemetry | replay 模式回放 CSV，订阅 telemetry topic | 收到含 `replay_progress_pct` 的 telemetry | progress 值随时间增长 |
| T07 | telemetry 字段完整性 | 检查任意一条 telemetry payload | 包含 device_id, mode, ts, point_count, sweep_point_count, min_distance_cm, reassembly 全部字段 | 无缺失字段 |
| T08 | 无数据时 telemetry | live 模式启动但无 CAN 数据 | point_count=0, min_distance_cm=null | 不崩溃 |

#### 9.2.3 Alarm 告警

| 编号 | 测试项 | 操作 | 预期结果 | 通过标准 |
| --- | --- | --- | --- | --- |
| T09 | MCU 原生告警触发 | 回放含告警点的 CSV（`status & 0x07 != 0`） | 收到 `alarm=true`，`alarm_source=mcu_status` | 收到 |
| T10 | 告警恢复 | 告警点过后恢复正常点 | 收到 `alarm=false`，`alarm_source=clear` | 收到 |
| T11 | 告警不重复 | 连续多个同等级告警点 | 只在告警状态首次变化时发布一次 | 不会每个点都发 |
| T12 | 无告警时不发 | 全部 `status=0` 且距离安全的 CSV | 不收到任何 alarm 消息 | 无误报 |
| T12A | 派生近距离告警 | live/replay 中最小距离进入 50cm / 30cm 阈值 | 收到 `alarm_source=derived_distance`，`alarm_reason=derived_near_obstacle` 或 `derived_too_near` | 收到 |
| T12B | 派生无有效点告警 | live/replay 中短时间无新增有效点 | 收到 `alarm_source=derived_no_valid_points`，`alarm_reason=derived_no_valid_points` | 收到 |

#### 9.2.4 Cmd 命令

| 编号 | 测试项 | 操作 | 预期结果 | 通过标准 |
| --- | --- | --- | --- | --- |
| T13 | ping 命令 | `mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"ping","req_id":"t13"}'` | 程序日志输出 `MQTT cmd: cmd=ping req_id=t13 result=OK` | 日志可见 |
| T14 | pause_replay | replay 模式下发送 pause_replay | 回放暂停 | 点云冻结 |
| T15 | resume_replay | 暂停后发送 resume_replay | 回放继续 | 点云恢复运动 |
| T16 | set_replay_speed | 发送 set_replay_speed speed=2.0 | 回放速度变为 2x | 可观察到加速 |
| T17 | 非法命令 | 发送 `{"cmd":"reboot"}` | 日志输出 REJECTED unknown_command | 不执行 |
| T18 | 模式不匹配 | live 模式下发送 pause_replay | 日志输出 REJECTED wrong_mode | 不执行 |
| T19 | 非法参数 | 发送 `{"cmd":"set_replay_speed","speed":5.0}` | 日志输出 REJECTED invalid_speed | 不执行 |

#### 9.2.5 回归测试

| 编号 | 测试项 | 操作 | 预期结果 | 通过标准 |
| --- | --- | --- | --- | --- |
| T20 | CAN 接收不受影响 | MQTT 开启状态下 live 模式接收 CAN | 点云正常显示、CSV 正常写入 | 行为与无 MQTT 时一致 |
| T21 | Replay 不受影响 | MQTT 开启状态下回放 CSV | 点云正常回放、时间轴正常工作 | 行为与无 MQTT 时一致 |
| T22 | MQTT 断线不影响主功能 | 关闭 Mosquitto 后运行程序 | CAN 接收、点云显示、CSV 写入、replay 全部正常 | 不崩溃不卡顿 |
| T23 | CSV 业务字段一致 | 对比 MQTT 开启前后生成的 CSV 文件 | CSV schema（字段顺序/名称/个数）、点数量、`seq/t_sample_us/angle_tick/angle_deg/distance_cm/x_mm/y_mm/quality/status` 等业务字段逐行一致。`host_rx_time_us` 和文件名路径允许因运行时间不同而自然差异 | 业务字段无差异 |
| T24 | Broker 未启动时程序正常 | 不启动 Mosquitto，直接运行程序 | 程序正常启动，功能正常，日志有连接失败提示但不阻塞 | 降级运行 |

### 9.3 调试命令速查

订阅所有 topic：

```bash
mosquitto_sub -h localhost -t "lidar/01/#" -v
```

只看 status：

```bash
mosquitto_sub -h localhost -t "lidar/01/status" -v
```

发送 ping 命令：

```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"ping","req_id":"debug1"}'
```

发送 pause_replay：

```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"pause_replay","req_id":"debug2"}'
```

发送 set_replay_speed：

```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"set_replay_speed","speed":2.0,"req_id":"debug3"}'
```

### 9.4 Mosquitto 安装（Ubuntu / Debian）

```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

默认配置即监听 localhost:1883，无需额外配置。如需允许局域网访问，编辑 `/etc/mosquitto/mosquitto.conf` 添加 `listener 1883 0.0.0.0` 和 `allow_anonymous true`。

### 9.5 Paho 安装

```bash
pip install paho-mqtt
```

或在项目虚拟环境中：

```bash
source can-venv/bin/activate
pip install paho-mqtt
```
