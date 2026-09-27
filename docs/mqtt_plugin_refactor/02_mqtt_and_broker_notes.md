# MQTT 与 Broker 设计说明

## 3. MQTT 基础概念与本项目映射

### 3.1 为什么这里用 MQTT

`MQTT` 是一种发布/订阅式消息协议，适合低带宽、弱连接、设备状态上报和轻量远程控制场景。

在本项目里，`MQTT` 不用来替代当前主链路。当前主链路仍然是：

```text
LiDAR
-> MCU
-> CAN
-> Linux 接收解析
-> 点云显示 / CSV 记录 / 回放
```

`MQTT` 的定位是挂在 `Linux` 输出层上的对外消息出口：

```text
Linux 核心处理结果
-> 状态摘要
-> 告警
-> 运行统计
-> MQTT 发布
```

这样做的好处是，后续即使 `MQTT` 断线、Broker 不存在、平台暂时不可用，也不应该影响当前雷达接收、显示、存储和回放。

### 3.2 Broker 是什么

`Broker` 是 `MQTT` 的消息中转服务器。

设备之间不是直接互相连接，而是都连接到 `Broker`：

```text
发布者 Publisher
-> Broker
-> 订阅者 Subscriber
```

在本项目里，可以这样理解：

- `Linux` 雷达程序是 `MQTT Client`。
- 本地 `Mosquitto` 可以作为开发阶段的 `Broker`。
- 平台、调试脚本、手机工具或另一个程序可以作为订阅者。
- 如果后续需要远程命令，平台或调试脚本也可以作为发布者，向命令 topic 发布消息。

### 3.3 Publish / Subscribe

`publish` 表示向某个 `topic` 发布一条消息。

例如 `Linux` 端发布当前状态：

```text
topic: lidar/01/status
payload: {"state":"online","mode":"live"}
```

`subscribe` 表示订阅某个 `topic`，当该 `topic` 有新消息时，客户端会收到回调。

例如 `Linux` 端订阅命令：

```text
topic: lidar/01/cmd
payload: {"cmd":"set_mode","mode":"replay"}
```

本项目里建议的方向是：

- `Linux` 发布状态、遥测摘要、告警。
- `Linux` 订阅少量命令。
- 命令只控制 `Linux` 侧行为，不直接改 `MCU` 协议。

### 3.4 Topic 是什么

`Topic` 是消息路径，用来表达消息属于哪个设备、哪类数据。

它类似一个层级字符串：

```text
lidar/01/status
lidar/01/telemetry
lidar/01/alarm
lidar/01/cmd
```

本项目的 topic 设计应遵循几个原则：

- 能区分设备，例如 `lidar/01`。
- 能区分消息类型，例如 `status`、`telemetry`、`alarm`、`cmd`。
- 不把全部点云塞进高频 topic。
- 后续如果接平台，topic 不要频繁改名。

具体 topic 和字段定义放在 [03_topic_interface_and_test.md](./03_topic_interface_and_test.md)。

### 3.5 Payload 是什么

`Payload` 是 topic 里真正传输的消息内容。

本项目建议使用 `JSON`，因为它方便调试，也方便平台或脚本读取。

示例：

```json
{
  "device_id": "lidar-01",
  "mode": "live",
  "point_count": 120,
  "min_distance_cm": 46,
  "alarm": false
}
```

注意，`Payload` 里不应该放过大的高频原始点云数组。第一版更适合放摘要信息，例如：

- 当前运行模式
- 最新点数量
- 最近一段时间最小距离
- 告警状态
- 重组统计
- 程序版本或运行状态

### 3.6 QoS 是什么

`QoS` 表示消息投递质量。

常见值有三个：

- `QoS 0`：最多发送一次，不保证一定到达。适合高频遥测摘要。
- `QoS 1`：至少到达一次，可能重复。适合状态、告警、命令。
- `QoS 2`：确保只到达一次，但开销更大。当前阶段一般不需要。

本项目建议：

| 消息类型 | 建议 QoS | 原因 |
| --- | --- | --- |
| `status` | `1` | 状态变化不高频，希望尽量送达 |
| `telemetry` | `0` | 周期摘要可以丢一两条，下一条会覆盖 |
| `alarm` | `1` | 告警重要，应该尽量送达 |
| `cmd` | `1` | 命令需要可靠一些，但要能处理重复 |

如果使用 `QoS 1`，接收端要注意命令可能重复到达，因此命令处理最好具备幂等性。

### 3.7 Retain 是什么

`retain` 表示 Broker 是否保存某个 topic 的最后一条消息。

如果某条消息设置了 `retain=true`，新的订阅者一上线就能立刻拿到最后状态。

本项目建议：

- `status` 可以考虑 `retain=true`，方便新客户端看到设备当前在线/离线状态。
- `telemetry` 一般不需要 retain。
- `alarm` 是否 retain 要谨慎，避免旧告警被误认为当前告警。
- `cmd` 不应 retain，否则新启动的设备可能误执行旧命令。

### 3.8 Will 是什么

`will` 全称是 Last Will and Testament，表示客户端异常断线时，Broker 代替它发布一条遗嘱消息。

本项目里可以用它表示 `Linux` 网关离线：

```text
topic: lidar/01/status
payload: {"state":"offline"}
retain: true
```

当 `Linux` 程序正常启动后，再发布：

```text
topic: lidar/01/status
payload: {"state":"online"}
retain: true
```

这样调试端或平台就能知道雷达网关当前是否在线。

## 4. Broker 与客户端方案

### 4.1 开发阶段 Broker 方案

开发阶段建议先使用本地 `Mosquitto`。

推荐结构：

```text
Linux 雷达程序
-> 连接本机或局域网 Mosquitto Broker
-> 发布 status / telemetry / alarm
-> 订阅 cmd
```

本地 broker 的优点是：

- 部署简单。
- 不依赖云平台。
- 方便用命令行工具调试。
- 出问题时容易判断是代码问题还是网络问题。

开发阶段可以先不启用复杂认证和 TLS，等本地流程稳定后再考虑用户名、密码、TLS 和平台地址。

### 4.2 Mosquitto 是什么

`Mosquitto` 是常用的开源 `MQTT Broker`。

它在本项目里的作用是本地消息中转站：

```text
Linux 程序 publish
-> Mosquitto
-> 调试终端 / 平台 / 其他订阅者 subscribe
```

常用调试方式包括：

```bash
mosquitto_sub -h localhost -t "lidar/01/#" -v
```

这条命令可以订阅 `lidar/01` 下面所有 topic。

也可以手动发布一条命令：

```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"ping"}'
```

这些命令只用于调试和验证，不代表最终程序接口已经冻结。

### 4.3 Paho 是什么

`Paho MQTT` 是 Python 里常用的 `MQTT Client` 库。

它在本项目里的作用是让 `Linux` 端程序连接 Broker，并完成：

- `connect`
- `publish`
- `subscribe`
- `on_connect`
- `on_message`
- `on_disconnect`

本项目已把它封装到 `can_mqtt.py` 中，不让 GUI、CAN 解析和 CSV 逻辑直接依赖 Paho。

### 4.4 Python Paho 的使用方式

概念上，Paho 客户端流程如下：

```text
创建 client
-> 设置 will
-> 设置回调
-> 连接 broker
-> 订阅 cmd topic
-> 启动网络循环
-> 周期性 publish 状态和遥测
```

后续代码中可以采用类似结构：

```python
client = mqtt.Client(client_id="lidar-01")
client.will_set("lidar/01/status", '{"state":"offline"}', qos=1, retain=True)
client.connect("localhost", 1883, keepalive=30)
client.subscribe("lidar/01/cmd", qos=1)
client.loop_start()
```

真正发布消息时，不建议在主接收循环里直接阻塞等待网络结果。更合适的方式是：

```text
核心处理层生成状态/摘要/告警
-> 放入输出队列
-> MQTT 输出模块异步发布
```

这样即使 Broker 断开，也不会拖慢 `CAN` 接收和点云显示。

### 4.5 本项目客户端角色划分

本项目里可以把客户端分为三类：

| 客户端 | 角色 | 说明 |
| --- | --- | --- |
| `Linux` 雷达程序 | 发布者 + 命令订阅者 | 发布状态、遥测、告警，订阅命令 |
| 调试终端 | 订阅者 + 命令发布者 | 使用 `mosquitto_sub/pub` 验证消息 |
| 后续平台 | 订阅者 + 命令发布者 | 接收设备状态，必要时下发简单命令 |

第一版重点实现 `Linux` 雷达程序这一侧，调试终端只用于验证。

### 4.6 本阶段建议配置

本阶段建议采用保守配置：

| 项目 | 建议 |
| --- | --- |
| Broker | 本机或局域网 `Mosquitto` |
| 端口 | `1883` |
| TLS | 暂不启用 |
| 用户名密码 | 可先不启用，后续再加 |
| Payload | `JSON` |
| `status` | `QoS 1`，可 retain |
| `telemetry` | `QoS 0`，不 retain |
| `alarm` | `QoS 1`，默认不 retain |
| `cmd` | `QoS 1`，不 retain |

### 4.7 和当前 Linux 程序的关系

当前 `Linux` 程序已经有以下能力：

- 接收 `CAN`
- 双帧重组
- 构建点数据
- 写入 `CSV`
- 回放 `CSV`
- 显示点云

`MQTT` 模块不应该重新实现这些能力。

正确关系是：

```text
当前 Linux 主链路
-> 产出统一点数据和统计信息
-> MQTT 模块读取摘要结果
-> 发布到 Broker
```

也就是说，`MQTT` 只消费现有结果，不反向干扰主链路。

### 4.8 本阶段不建议做的用法

本阶段不建议：

- 用 `MQTT` 传全量高频原始点云。
- 让 `MQTT` 命令直接控制 `MCU` 协议。
- 在 `CAN` 接收循环里直接阻塞发布网络消息。
- 把 Broker 当作数据库。
- 把平台对接逻辑写死在点云解析模块里。
- 为了 `MQTT` 重写现有解析、显示、CSV 和回放逻辑。

`MQTT` 的正确位置是输出插件，不是主链路核心。
