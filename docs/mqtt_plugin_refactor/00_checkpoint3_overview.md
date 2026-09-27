# Checkpoint3 MQTT 插件计划

## 文档目的

本组文档用于说明 Checkpoint3 阶段为什么要在现有 `Linux` 端程序上预留 `MQTT` 插件能力，以及这次重构的边界、模块划分和验收方式。

当前项目已经完成 `MCU -> CAN -> Linux` 的基础闭环，包括实时接收、解析、点云显示、`CSV` 存储和历史回放。Checkpoint3 的重点不是重新打通主链路，而是在不破坏现有能力的前提下，让 `Linux` 端具备对外发布状态、遥测摘要、告警和简单命令入口的能力。

## 当前边界

本阶段的边界如下：

- 不修改 `MCU` 代码。
- 不修改现有 `CAN` 双帧协议。
- 不把 `MQTT` 作为高频原始点云传输通道。
- 不接入 `ESP32`。
- 不接入正式云平台。
- 不做复杂前端或远程控制面板。
- `MQTT` 只作为 `Linux` 输出层插件预留和实现。

## 文档索引

- [01_architecture_and_scope.md](./01_architecture_and_scope.md)：说明整体架构、当前范围、`MQTT` 挂载位置，以及当前阶段不做什么。
- [02_mqtt_and_broker_notes.md](./02_mqtt_and_broker_notes.md)：解释 `MQTT`、`Broker`、`Topic`、`Payload`、`QoS`、`retain`、`will`、`Mosquitto` 和 `Paho`，并映射到本项目。
- [03_topic_interface_and_test.md](./03_topic_interface_and_test.md)：定义后续 `Topic`、消息字段、命令边界、运行流程和测试验收计划。
- [04_ai_prompt_workflow.md](./04_ai_prompt_workflow.md)：整理成可以直接发给 AI 的分步 prompt，按”先拆层、再合同、再 MQTT”的顺序推进。
- [06_m6_5_phase_b_closed_loop.md](./06_m6_5_phase_b_closed_loop.md)：M6.5 Phase B Mosquitto + Paho 最小闭环验证步骤与结果记录。
- [07_module_architecture.md](./07_module_architecture.md)：当前代码的分层架构、模块职责、数据流与接口契约。
- [08_m6_5_verification_record.md](./08_m6_5_verification_record.md)：M6.5 全阶段验收记录、Notion 勾选项与待验证项。
- [09_windows_replay.md](./09_windows_replay.md)：Windows 回放入口与 Windows live CAN backend 说明。
- [10_m6_5_windows_board_mqtt.md](./10_m6_5_windows_board_mqtt.md)：Windows 上板 live CAN + MQTT 最小闭环验证记录。
