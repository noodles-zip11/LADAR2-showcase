# AI 分步实施 Prompt 手册

## 文档目的

这份文档不是设计说明，而是执行手册。

用途只有一个：把 M6.5 这部分拆成多个小步骤，每一步都整理成可以直接发给 AI 的 prompt，避免一次性把“重构 + MQTT + UI + 命令 + 测试”全部扔给 AI，导致改动失控。

## 使用原则

每次只发一个 prompt，不要合并多个阶段。

每一步都要满足下面四条：

- 明确本步目标。
- 明确本步不要做什么。
- 明确哪些行为必须保持不变。
- 明确本步做完后的验证方式。

建议你每次给 AI 的任务都要求它输出这三项：

1. 改了哪些文件
2. 为什么这样改
3. 怎么验证没有回归

## 统一约束

下面所有 prompt 都默认带上这些约束，除非你后续明确修改：

- 不修改 `MCU` 代码
- 不修改当前 `CAN` 主协议
- 不修改 `0x123 / 0x124` 的语义
- 不把正式字段 `distance_cm` 改名成 `distance_mm`
- 不混淆 `host_rx_time_us` 和 `t_sample_us`
- 不在前几步顺手加入 `MQTT`
- 不在前几步顺手重做 UI
- 不破坏当前 `CSV` 输出格式
- 不破坏 replay 模式

## Prompt 1：先出四层施工图，不改代码

```text
这是一个已经可以运行的现有工程。

当前目标只做：阅读现有 Linux 端代码，给出按 input / parser / core / output 四层拆分的重构方案。

当前代码重点文件：
- can_recv4.py

要求：
- 先只读代码，不要改任何文件
- 明确现有类、函数、逻辑分别属于哪一层
- 给出建议的新目录结构和文件划分
- 标出第一轮重构哪些代码必须保持不动
- 标出哪些模块适合先拆，哪些模块应该后拆

不要做：
- 不要改代码
- 不要加入 MQTT
- 不要修改 UI
- 不要修改 CSV 格式
- 不要修改 CAN 协议

请输出：
1. 现有代码的四层归类表
2. 建议的新文件结构
3. 第一轮重构顺序
4. 每一轮的风险点
5. 第一轮最小可行改造范围
```

## Prompt 2：先写 03 合同文档，不改代码

```text
现在不要改代码，只完善文档。

目标：
完善 docs/mqtt_plugin_refactor/03_topic_interface_and_test.md，
把它写成后续编码的合同文档。

请基于当前项目，定义以下内容：
- 统一点对象字段
- 派生字段
- MQTT topic：status / telemetry / alarm / cmd
- 每个 topic 的 payload 示例
- 第一版允许的命令
- 测试与验收项

约束：
- 保持现有正式字段语义不变
- 正式字段优先使用 host_rx_time_us / t_sample_us / angle_tick / angle_deg / distance_cm / quality / status
- distance_mm 只能作为内部派生量，不作为正式协议字段替代 distance_cm
- 第一版不上传全量原始点云
- 第一版命令只允许少量 Linux 侧命令

不要做：
- 不要改 Python 代码
- 不要改 MCU
- 不要引入 ESP32
- 不要接云平台

请输出：
1. 填完整的 03 文档
2. topic 表
3. payload 示例表
4. 命令白名单
5. 测试与验收清单
```

## Prompt 3：只拆 parser 层

```text
现在开始改代码，但当前只做 parser 层拆分。

目标：
从 can_recv4.py 中抽出 CAN 双帧重组和协议解析逻辑，拆成单独 parser 模块。

要求：
- 最小改动原则
- 保持现有行为不变
- 保持现有字段语义不变
- 保持现有 CSV 输出格式不变
- 保持 replay 模式可运行

优先拆分内容：
- CanPointAssembler
- 双帧协议解析
- 点对象构造前的解析逻辑

不要做：
- 不要加入 MQTT
- 不要修改 UI
- 不要重构 input 层
- 不要改 telemetry/alarm 逻辑
- 不要改主协议字段名

改完后请输出：
1. 改了哪些文件
2. parser 层新结构
3. 主程序入口如何接回 parser
4. 如何验证功能无回归
```

## Prompt 4：只拆 input 层

```text
当前只做 input 层拆分。

目标：
把当前 Linux 端输入来源拆成独立输入层，至少区分：
- live CAN input
- CSV replay input

如果串口输入暂时没有实现，请预留接口，但不要强行做完整功能。

要求：
- 保持现有 live 和 replay 行为不变
- 保持 parser 层接口可用
- 不修改 CSV 文件格式
- 不修改 UI 逻辑

不要做：
- 不要加入 MQTT
- 不要重做 controller
- 不要改核心几何计算
- 不要顺手改 output 层

改完后请输出：
1. input 层新文件结构
2. live / replay 分别怎么接入
3. 串口输入接口预留方式
4. 验证方法
```

## Prompt 5：只拆 core 层

```text
当前只做 core 层拆分。

目标：
把纯业务计算和数据处理逻辑从 can_recv4.py 中抽出，形成 core 层。

重点包括：
- 点云几何换算
- sweep / recent scan 提取
- 点统计
- 最小距离提取
- 后续 telemetry / alarm 的计算入口

要求：
- core 层只处理数据，不直接依赖 UI、CSV、MQTT
- 最小改动原则
- 保持现有可视化输入数据结构可继续使用

不要做：
- 不要改 UI 样式
- 不要加入 MQTT
- 不要修改 parser 契约
- 不要改 CAN 协议和字段名

改完后请输出：
1. core 层文件划分
2. 哪些函数迁移到了 core
3. core 输出了哪些对象或结果
4. 验证方式
```

## Prompt 6：只拆 output 层，MQTT 先留空壳

```text
当前只做 output 层拆分。

目标：
把现有输出逻辑拆成可插拔的 output 层，至少拆出：
- ui_output
- csv_output
- log_output

同时预留 mqtt_output 文件和接口，但当前不要接 broker，不要真正发布消息。

要求：
- UI 继续能显示
- CSV 继续能写
- 日志输出继续可用
- mqtt_output 当前只做空壳接口或占位类

不要做：
- 不要接入 Paho
- 不要连接 Mosquitto
- 不要修改主协议
- 不要在这一步重做 UI 布局

改完后请输出：
1. output 层结构
2. UI / CSV / log 分别如何接入
3. mqtt_output 预留了什么接口
4. 如何验证无回归
```

## Prompt 7：单独做 MQTT 最小闭环，不接主程序

```text
当前不要改主程序，只写一个独立的 MQTT 最小测试脚本。

目标：
新增一个 mqtt_smoke_test.py，用 Paho MQTT 连接本机 Mosquitto，跑通最小闭环：
- publish 一条 telemetry
- subscribe 一条 cmd
- 收到 cmd 后打印回调

要求：
- 独立脚本
- 不依赖主程序重构完成
- 给出安装依赖和运行方式
- payload 使用 JSON

不要做：
- 不要接入现有 UI
- 不要接入现有 CAN 主循环
- 不要写复杂命令系统
- 不要上传全量点云

请输出：
1. 新增脚本
2. 运行命令
3. mosquitto_sub / mosquitto_pub 调试命令
4. 成功时会看到什么现象
```

## Prompt 8：把 mqtt_output 接回主程序

```text
现在在前面重构完成的基础上，把 MQTT 作为 output 层插件接入主程序。

目标：
- 程序启动后发布 status online
- 周期发布 telemetry
- 告警变化时发布 alarm
- 订阅 cmd
- 异常断开时使用 will 发布 offline

要求：
- MQTT 只存在于 output 层
- 不反向侵入 parser / core
- 不阻塞 CAN 接收和 replay
- 建议使用异步 loop_start 或等效方式

建议默认：
- status: QoS 1, retain true
- telemetry: QoS 0
- alarm: QoS 1
- cmd: QoS 1, retain false

不要做：
- 不要上传全量原始点云
- 不要让 MQTT 直接控制 MCU 协议
- 不要把平台逻辑写死在 core

改完后请输出：
1. mqtt_output 如何接入
2. 新增配置项
3. 发布了哪些 topic
4. 如何验证主程序最小闭环
```

## Prompt 9：只做第一版命令白名单

```text
当前只做第一版命令系统，不扩展成复杂远程控制。

目标：
为主程序实现最小命令白名单，只允许少量 Linux 侧命令，例如：
- ping
- pause_replay
- resume_replay
- set_replay_speed

要求：
- 命令只影响 Linux 侧行为
- 不修改 MCU 协议
- 命令处理尽量幂等
- 非法命令要给出日志或回执

不要做：
- 不要做复杂权限系统
- 不要做平台接入
- 不要做硬件级控制
- 不要扩展成几十个命令

改完后请输出：
1. 命令白名单实现
2. 命令 payload 示例
3. 收到非法命令时的行为
4. 验证方法
```

## Prompt 10：最后再补 UI 面板

```text
当前只做 UI 信息面板增强，不改主视图定位。

目标：
保留现有 2D 点云主视图，在此基础上补充：
- 状态面板
- telemetry 摘要
- alarm 区
- replay 控制相关信息

要求：
- 保留现有实时 2D 点云作为主视图
- 不为了 UI 重写 parser / core / output
- 信息面板优先展示少量高价值指标

不要做：
- 不要做复杂 IoT 大屏
- 不要做平台前端
- 不要在这一步再改 MQTT 协议

改完后请输出：
1. UI 改了哪些区域
2. 增加了哪些指标
3. 如何验证桌面端可用性
```

## 通用收尾 Prompt

当某一步完成后，你可以再追加一个统一收尾 prompt：

```text
请对这一步改动做收尾说明。

要求输出：
1. 本步改了哪些文件
2. 本步完成了什么
3. 本步刻意没有做什么
4. 当前剩余风险
5. 下一步最合理的任务是什么
```

## Prompt 11：M6.5 阶段 A，不上板先闭合代码合同

```text
当前任务属于 M6.5 的阶段 A：不上板、不接真实 CAN 硬件，先把 Linux 端代码和 MQTT 合同闭合。

当前项目已经接受根目录 can_*.py 拆法，不再要求改成 lidar/ 包结构。

当前真实结构：
- can_recv4.py：主入口 + PySide6 UI + 调度逻辑
- can_input.py：CAN live 输入、CSV replay 输入、输入辅助函数
- can_parser.py：CAN 双帧解析、LidarPoint、CSV 字段常量、compute_xy_mm
- can_core.py：几何与 sweep 相关纯计算
- can_output.py：CSV 输出与格式化
- can_mqtt.py：MQTT 输出插件与命令分发
- mqtt_smoke_test.py：本机 MQTT 最小闭环脚本

目标：
1. 修复 alarm 触发入口，满足 docs/mqtt_plugin_refactor/03_topic_interface_and_test.md 的合同要求：
   - alarm 不依赖 telemetry 周期
   - alarm 不只依赖 render_scene
   - 每个新 LidarPoint 进入时要立即检查告警状态
   - 短暂告警：正常点 -> 告警点 -> 正常点，即使发生在两次 render 之间，也不能漏报
2. 补一个不上板可运行的 replay alarm 验证路径。
3. 补 MQTT 合同静态/轻量自检，不依赖本机 Mosquitto。
4. 同步文档边界：can_*.py 是当前正式拆法；串口输入是预留，不纳入 M6.5 阶段 A 验收。

允许修改：
- can_recv4.py
- can_mqtt.py
- can_input.py / can_core.py / can_parser.py（仅当为了测试或小接口必须）
- tools/ 下新增或更新自检脚本
- docs/mqtt_plugin_refactor/ 下同步文档

优先实现：
1. 在 can_recv4.py 中抽出 alarm 检查函数，例如：
   - _check_and_publish_alarm(point)
   - 或等价命名
2. live 模式：
   - 在 ingest_live_point(point) 中写入 live_points / CSV 后，立即调用 alarm 检查函数。
3. replay 模式：
   - 不要只靠 render_scene 的 latest_point。
   - 在 replay 时间推进时，识别新进入时间窗口或新越过的点，并对这些点调用 alarm 检查函数。
   - 如果实现复杂，先用最小可行方式：维护 replay_last_alarm_index，只对上次位置到当前 replay_current_us 之间新增经过的点逐个检查。
4. render_scene：
   - 保留 UI 显示。
   - 保留 telemetry 2 秒节流发布。
   - 不再作为 alarm 的唯一发布入口。
5. alarm payload 必须符合 03 合同：
   - device_id
   - ts
   - alarm
   - alarm_status
   - alarm_description
   - latest_point.distance_cm
   - latest_point.angle_deg
   - latest_point.quality
   - latest_point.status
6. MQTT 合同自检至少覆盖：
   - status online payload 字段
   - status offline payload 字段
   - telemetry payload 字段
   - alarm payload 字段
   - set_replay_speed 只允许 0.5 / 1.0 / 2.0
   - disconnect 使用 wait_for_publish(timeout=1.0) 或等价等待

不要做：
- 不要修改 MCU 代码
- 不要修改 CAN 0x123 / 0x124 协议
- 不要接真实 CAN 硬件
- 不要要求上板测试
- 不要安装或依赖 Mosquitto
- 不要接云平台
- 不要引入 ESP32
- 不要上传全量原始点云到 MQTT
- 不要把 distance_cm 改名为 distance_mm
- 不要把 host_rx_time_us 和 t_sample_us 混用
- 不要重写整个 UI
- 不要把 can_*.py 改成 lidar/ 包结构

验证方式：
1. 语法检查：
   python -m py_compile can_recv4.py can_parser.py can_input.py can_core.py can_output.py can_mqtt.py mqtt_smoke_test.py

2. 现有自检：
   powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1

3. 新增或更新的不上板自检：
   - 必须能证明 replay 中 正常点 -> 告警点 -> 正常点 会生成 alarm=true 和 alarm=false 两次状态变化。
   - 必须能证明 MQTT payload 字段符合 03 合同。

4. 不要求本阶段跑 Mosquitto。
   Mosquitto + Paho 最小闭环放到阶段 B。

改完后请输出：
1. 改了哪些文件
2. alarm 入口现在在哪里触发
3. replay 如何避免短暂告警漏报
4. MQTT 合同自检覆盖了哪些字段
5. 运行了哪些验证命令，以及结果
6. 哪些内容仍然留到阶段 B 或上板阶段
```

## Prompt 12：M6.5 阶段 B，本机 Mosquitto + Paho 最小闭环

```text
当前任务属于 M6.5 的阶段 B：不上板、不接真实 CAN 硬件，只验证本机 MQTT 软件闭环。

前提：
- 阶段 A 已经完成或至少不阻塞 MQTT payload 合同。
- 本阶段允许安装或使用本机 Mosquitto。
- 本阶段不接真实 CAN 硬件，不做上板测试。

目标：
1. 跑通本机 Mosquitto + Paho 最小闭环。
2. 验证 mqtt_smoke_test.py 能发布 status / telemetry，并订阅 cmd。
3. 验证 can_recv4.py 在 replay 模式下能通过 MQTT 发布：
   - status online / offline
   - telemetry
   - alarm
   - cmd 回调日志
4. 留下可复制的最小闭环日志，作为 M6.5 验收证据。

允许修改：
- mqtt_smoke_test.py
- can_mqtt.py（仅修 MQTT 闭环相关小问题）
- can_recv4.py（仅修 replay + MQTT 闭环相关小问题）
- docs/mqtt_plugin_refactor/ 下补运行记录或说明

不要做：
- 不要接真实 CAN
- 不要修改 MCU
- 不要修改 CAN 0x123 / 0x124 协议
- 不要引入 ESP32
- 不要接云平台
- 不要上传全量原始点云
- 不要重构 UI
- 不要重写 parser / input / core / output 架构

执行步骤：
1. 检查 Mosquitto 是否可用：
   - mosquitto
   - mosquitto_pub
   - mosquitto_sub

2. 如果不可用，给出本机安装方式。
   - Linux / WSL:
     sudo apt install mosquitto mosquitto-clients
   - Windows:
     说明使用 Mosquitto Windows 安装包或通过 WSL 验证。

3. 启动或确认 broker 正在监听 localhost:1883。

4. 终端 A 订阅：
   mosquitto_sub -h localhost -t "lidar/01/#" -v

5. 终端 B 运行：
   python mqtt_smoke_test.py

6. 终端 C 发送命令：
   mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"ping\",\"req_id\":\"t13\"}" -q 1

7. 记录必须出现的现象：
   - status online payload
   - telemetry payload
   - cmd 被 mqtt_smoke_test.py 收到并打印
   - 退出时 status offline payload

8. replay + 主程序验证：
   - 使用现有 CSV fixture 或最小 replay CSV。
   - 启动 can_recv4.py 的 replay 模式。
   - 订阅 lidar/01/#。
   - 发送 ping / pause_replay / resume_replay / set_replay_speed。
   - 记录主程序日志里的 MQTT cmd 行。

验收标准：
- status online 字段符合 03 合同。
- status offline 字段符合 03 合同。
- telemetry 字段符合 03 合同。
- cmd 回调可观测。
- set_replay_speed 只接受 0.5 / 1.0 / 2.0。
- 正常退出能发布 offline。

改完或跑完后请输出：
1. Mosquitto 是否已可用
2. 运行了哪些命令
3. 订阅端看到的 status / telemetry / offline 示例
4. cmd 回调日志
5. 是否还存在需要上板才能验证的项
```

## Prompt 13：M6.5 阶段 C，UI 与文档证据收口

```text
当前任务属于 M6.5 的阶段 C：不上板，用 replay 和本机软件环境补齐 UI 与文档证据。

前提：
- 阶段 A 已经完成代码合同闭合。
- 阶段 B 已经完成或至少明确 MQTT 软件闭环状态。
- 本阶段不接真实 CAN 硬件。

目标：
1. 用 replay 模式补 UI 截图或录屏证据。
2. 同步文档，使文档和当前真实代码结构一致。
3. 明确哪些 M6.5 项已经完成，哪些留到上板或后续阶段。
4. 为 Notion 打勾提供证据依据。

当前正式结构：
- can_recv4.py：主入口 + UI + 调度
- can_input.py：输入层
- can_parser.py：解析层
- can_core.py：核心计算
- can_output.py：CSV 输出
- can_mqtt.py：MQTT 输出
- mqtt_smoke_test.py：MQTT 软件闭环脚本

允许修改：
- docs/mqtt_plugin_refactor/*.md
- README 或运行说明文档（如果已有相关位置）
- 可以新增一份 M6.5 验收记录 md
- 不改代码，除非发现文档截图流程中暴露出小的明显 bug

不要做：
- 不要接真实 CAN
- 不要修改 MCU
- 不要修改 CAN 协议
- 不要继续扩 MQTT 协议
- 不要把 can_*.py 改成 lidar/ 包结构
- 不要把串口输入写成已完成，除非真的实现并验证

需要补齐的文档内容：
1. Linux 分层架构说明：
   - 说明为什么接受 can_*.py 拆法。
   - 说明每个 can_*.py 文件职责。
   - 说明 can_recv4.py 仍是主入口和 UI 容器。

2. 模块接口说明：
   - input 输出什么
   - parser 输出 LidarPoint
   - core 提供哪些纯计算
   - output / mqtt 如何消费摘要和状态

3. MQTT topic 与 payload 定义表：
   - 链接或引用 03_topic_interface_and_test.md
   - 确认 status / telemetry / alarm / cmd 与代码一致

4. 串口输入边界：
   - 当前只预留，不纳入 M6.5 验收。
   - 不把“串口已兼容”作为完成项。

5. UI 证据：
   - replay 模式下截图或录屏
   - 必须能看到 2D 点云、状态面板、告警区、回放控制
   - 如果 MQTT broker 可用，截图中最好能看到 MQTT 状态

6. 验收记录：
   - py_compile 命令和结果
   - selfcheck_all.ps1 结果
   - MQTT smoke test 结果（如果阶段 B 已完成）
   - replay alarm fixture 结果（如果阶段 A 已完成）

验收后建议 Notion 可勾选：
- 已完成且有证据的项才勾。
- 串口输入不勾，或改为“串口预留，不纳入 M6.5 验收”。
- Mosquitto 闭环只有阶段 B 跑通后才勾。
- UI 重构只有截图/录屏能证明后才勾。

改完后请输出：
1. 更新了哪些文档
2. 当前 M6.5 哪些项可勾
3. 哪些项仍不能勾，以及原因
4. 截图/录屏或日志证据路径
5. 下一步是否进入上板验证
```

## Prompt 14：M6.5 本地剩余四项收口（不上板）
```text
当前任务属于 M6.5 的本地收口阶段，不上板、不接真实 CAN 硬件。

背景：
- 当前已经完成 can_*.py 的基本拆分。
- 已经冻结 MQTT topic / payload 合同。
- 已经跑通本机 Mosquitto + Paho 最小闭环。
- 但是 Notion 里仍有 4 个 M6.5 checkbox 不能严格打勾，因为它们只是部分完成：
  1. 统一输入层，兼容 CAN、串口与 CSV 回放三类数据源。
  2. 核心层固化业务计算：点云变换、扇区统计、最小距离、告警判定、设备状态汇总。
  3. 输出层提供可替换适配器：ui_output、csv_output、log_output、mqtt_output。
  4. 重构 UI：保留实时 2D 点云，并补状态面板、扇区摘要、告警区与回放控制。

目标：
把上面 4 个 checkbox 做到“不上板也可以验收”的程度。

重要边界：
- 不改 MCU。
- 不改 CAN 0x123 / 0x124 协议。
- 不引入 ESP32。
- 不接云平台。
- 不上传全量原始点云到 MQTT。
- 不为了追求完美大改架构。
- 可以保留 can_recv4.py 作为主入口和 UI 容器，但业务计算、输入源、输出适配器边界要更清楚。

允许修改：
- can_input.py
- can_core.py
- can_output.py
- can_mqtt.py
- can_recv4.py
- tools/selfcheck_*.py
- docs/mqtt_plugin_refactor/*.md

一、统一输入层收口

目标：
让 input 层至少具备统一接口，而不是只有 open_bus() 和 CsvReplaySource 两个分散概念。

要求：
1. 在 can_input.py 中定义清晰的输入源接口或最小协议，例如：
   - close()
   - 读取/推进数据的方法
   - source_name / mode / stats 等最小信息
2. 保留现有 CAN live 能力。
3. 保留现有 CSV replay 能力。
4. 串口输入可以先做 mock / stub / reserved adapter，但不能只停留在注释。
   - 如果不实现真实串口读数据，必须明确类名、构造参数、当前状态和 NotImplemented 边界。
   - 不要声称真实串口已经完成。
5. can_recv4.py 中的数据源选择逻辑要能清楚对应 CAN / replay / serial-reserved 三类输入。

验收：
- py_compile 通过。
- selfcheck 中能验证 input 层存在 CAN、CSV、Serial reserved 三类入口。
- 文档明确：串口是真实预留还是 mock，不伪装成硬件完成。

二、core 业务计算收口

目标：
把 telemetry / alarm / sector / min distance / device summary 的纯计算从 UI 里尽量移到 can_core.py。

要求：
1. can_core.py 中新增或完善纯函数：
   - compute_min_distance(points)
   - compute_sector_summary(points, sector_definitions 或默认扇区)
   - compute_device_summary(mode, points, latest_point, reassembly, replay_progress 等)
   - compute_alarm_state(point 或 latest_point)
   - build_telemetry_payload(...) 或返回 telemetry 所需字段的 summary dict
2. 这些函数不能依赖 PySide6、pyqtgraph、Paho、CSV 文件句柄。
3. can_recv4.py 只负责拿 core 的结果去刷新 UI 或发布 MQTT。
4. 保留每个 accepted LidarPoint 进入时立即检查 alarm 的行为，不能退回只在 render_scene 里检查。
5. 扇区统计至少要有一个最小可用版本，例如 front / left / right / rear 或按角度段统计：
   - point_count
   - min_distance_cm
   - alert_level

验收：
- 新增或更新 selfcheck_core / selfcheck_contract，覆盖：
  - 空点集
  - 正常点集最小距离
  - 告警点 status & 0x07
  - ESTIMATED bit 0x08 不影响 alert level
  - 扇区统计能稳定输出
- selfcheck_all.ps1 通过。

三、output adapter 收口

目标：
让输出层从“几个文件里散落的输出类”变成可以解释为 adapter 的结构。

要求：
1. 在 can_output.py 中定义最小输出适配器边界，例如：
   - CsvOutputAdapter / CsvPointWriter
   - LogOutputAdapter
   - UiOutputAdapter 可以是文档化/轻量包装，若 UI 仍在 can_recv4.py，必须明确其边界
2. can_mqtt.py 作为 mqtt_output adapter，文档和命名要一致。
3. 不要求把 PointCloudWindow 整个搬出 can_recv4.py，但要避免文档继续说 ui_output 已经独立完成。
4. output adapter 的职责必须是“消费点、summary、状态”，不能反向修改 parser/input 协议。

验收：
- selfcheck 能确认 CSV / log / MQTT adapter 的存在和基本方法。
- 文档说明哪些 adapter 已实装，哪些只是边界保留。
- 不再出现 output_mqtt.py / mqtt_gateway.py 这类旧命名。

四、UI 剩余收口

目标：
让 UI checkbox 能打勾：实时 2D 点云、状态面板、扇区摘要、告警区、回放控制都可见。

要求：
1. 保留现有 2D 点云主视图。
2. 状态面板至少显示：
   - mode
   - point_count
   - sweep_point_count
   - min_distance
   - MQTT status
   - alarm status
3. 新增或补齐“扇区摘要”区域：
   - 至少显示 3~4 个扇区
   - 每个扇区显示 point_count / min_distance / alert
4. 告警区必须能从 latest/current point 的 status 反映正常或告警。
5. 回放控制必须保留：
   - 选择 CSV
   - 播放/暂停
   - 速度 0.5x / 1x / 2x
   - 时间轴
6. 用 replay CSV 生成截图或 offscreen screenshot 作为证据。

验收：
- 能在无硬件环境用 replay CSV 打开 UI。
- 能生成或保存 UI 截图。
- 截图能看到 2D 点云、状态面板、扇区摘要、告警区、回放控制。

五、文档与 Notion 对齐

要求更新：
- docs/mqtt_plugin_refactor/07_module_architecture.md
- docs/mqtt_plugin_refactor/08_m6_5_verification_record.md
- 必要时更新 03_topic_interface_and_test.md 和 04_ai_prompt_workflow.md

验收结论要明确分三类：
1. 可以打勾：
   - 统一输入层
   - core 业务计算
   - output adapter
   - UI 重构
2. 仍留到上板：
   - live 模式真实 CAN + MQTT
   - 真实硬件告警触发
   - 长时间真实运行稳定性
   - broker 断开时真实 live 主链路不受影响
3. 不属于 M6.5：
   - ESP32
   - 云平台
   - 全量原始点云 MQTT 上传

完成后请输出：
1. 修改了哪些代码文件。
2. 新增或更新了哪些 selfcheck。
3. 跑了哪些命令，结果是什么。
4. 4 个 checkbox 是否可以打勾。
5. 哪些内容仍必须留到上板。
```

## Prompt 15：M6.5 阶段 D，上板前后硬件验证

```text
当前任务属于 M6.5 的阶段 D：最后集中做上板或真实 CAN 硬件验证。

前提：
- 阶段 A/B/C 已经尽量完成不上板可做的内容。
- 本阶段允许接真实 CAN 硬件和雷达板。
- 本阶段只验证 Linux 重构与 MQTT 底座是否不破坏主链路，不扩展新功能。

目标：
1. 验证 live 模式真实 CAN 接收仍正常。
2. 验证 CSV 写入仍正常。
3. 验证 2D 点云实时显示仍正常。
4. 验证 MQTT 在 live 模式下发布 status / telemetry / alarm 不阻塞主链路。
5. 验证正常关闭 offline。
6. 记录硬件验证日志，作为 M6.5 最终收口证据。

允许修改：
- 原则上先不改代码，只做验证。
- 如果发现小 bug，只做最小修复。
- 不做新功能扩展。

不要做：
- 不改 MCU 协议
- 不改 CAN 0x123 / 0x124 语义
- 不引入 ESP32
- 不接云平台
- 不上传全量原始点云
- 不在硬件验证阶段顺手重构 UI 或 MQTT 协议

验证步骤：
1. 准备环境：
   - CAN 设备可用
   - socketcan 通道可用，例如 can0
   - Mosquitto broker 可选但推荐开启

2. 启动订阅端：
   mosquitto_sub -h localhost -t "lidar/01/#" -v

3. 启动 live 模式：
   python can_recv4.py --mode live --channel can0

4. 观察并记录：
   - UI 是否显示实时 2D 点云
   - 状态面板是否更新
   - CSV 是否写入
   - summary 是否在退出后生成
   - telemetry 是否周期发布
   - MQTT 断开或 broker 不可用时是否不影响 CAN/UI/CSV

5. 告警验证：
   - 如果真实硬件能触发 status & 0x07 != 0，则记录 alarm=true / alarm=false。
   - 如果现场无法稳定触发，标记为“真实告警场景待构造”，不要伪造上板结论。

6. 正常关闭：
   - 关闭窗口或 Ctrl+C。
   - 验证 offline retained status 是否发布。

7. 归档证据：
   - CAN live 日志片段
   - CSV 输出文件路径
   - summary 文件路径
   - MQTT 订阅日志
   - UI 截图或短录屏
   - 若有告警，归档 alarm 日志

验收标准：
- live 模式可运行。
- CAN 接收、CSV 写入、2D UI 不因 MQTT 破坏。
- MQTT telemetry 不阻塞主链路。
- 正常关闭 offline 可见。
- 无法上板验证的内容必须明确标记，不假装完成。

完成后请输出：
1. 硬件环境和运行命令
2. live 模式是否正常
3. CSV / summary 输出证据
4. MQTT status / telemetry / offline 证据
5. alarm 是否完成真实硬件验证
6. 仍需后续 M5/M6 长稳或几何质量验证的内容
```
