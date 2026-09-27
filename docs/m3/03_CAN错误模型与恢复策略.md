# M3 CAN 错误模型与恢复策略

## 1. 目标

冻结 M3 第一版 CAN 错误处理口径，明确：

- `AutoBusOff` 是否开启
- 是否采用手动 `HAL_CAN_Stop()` / `HAL_CAN_Start()`
- `recovery` 的定义
- 哪些错误只计数不干预
- 字段表中的 CAN 错误字段如何对应到运行时行为

本页只冻结策略，不涉及代码实现。

## 2. 当前代码现状

截至 2026-03-28，当前工程中的 CAN 相关状态如下：

- [Core/Src/can.c](/C:/biancheng/STM32HAL/LADAR2/Core/Src/can.c)
  - `hcan1.Init.AutoBusOff = ENABLE`
  - `hcan1.Init.AutoRetransmission = ENABLE`
- [Core/Src/freertos.c](/C:/biancheng/STM32HAL/LADAR2/Core/Src/freertos.c)
  - 已调用 `HAL_CAN_Start(&hcan1)`
  - 已调用 `HAL_CAN_ActivateNotification(...)`
- [Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_can.h](/C:/biancheng/STM32HAL/LADAR2/Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_can.h)
  - 已提供 `HAL_CAN_ErrorCallback()`
  - 已提供 `HAL_CAN_GetError()`
  - 已定义 `CAN_IT_ERROR_WARNING`、`CAN_IT_ERROR_PASSIVE`、`CAN_IT_BUSOFF`、`CAN_IT_LAST_ERROR_CODE`、`CAN_IT_ERROR`

当前代码已经完成的最小闭环包括：

- `HAL_CAN_ErrorCallback()` 负责记录错误快照和 `Bus-Off` 进入
- `CAN_DiagPoll()` 负责轮询 `Bus-Off` 结束并累计 recovery
- `CAN1_SCE_IRQHandler()` 已接入 HAL

这意味着当前工程已经具备 M3 所需的最小 CAN 错误统计入口，并且这些字段已经接入 `DiagLogTask` 的 M3 CSV 输出。

## 3. 以字段表为基础的设计约束

本页的所有建议，都以 [02_DiagLogTask字段表.md](/C:/biancheng/STM32HAL/LADAR2/docs/m3/02_DiagLogTask字段表.md) 中已经冻结的 4 个字段为基础：

- `can_last_error_code`
- `can_error_irq_cnt`
- `can_bus_off_cnt`
- `can_recovery_cnt`

因此本页策略必须满足以下约束：

- `can_last_error_code` 表示最近一次观测到的 HAL CAN 错误位图
- `can_error_irq_cnt` 表示错误回调进入次数，而不是“恢复次数”
- `can_bus_off_cnt` 只统计进入 `Bus-Off` 的 episode 数
- `can_recovery_cnt` 只统计从 `Bus-Off` 成功恢复的 episode 数

如果恢复策略设计得太激进，例如对一般错误也主动 `Stop/Start`，这 4 个字段的语义会被搅乱，后续日志无法稳定分析。

## 4. AutoBusOff 是什么

`AutoBusOff` 是 bxCAN 的自动 Bus-Off 管理开关，对应 HAL 初始化结构体里的：

- `CAN_InitTypeDef.AutoBusOff`

它的含义可以直接理解为：

- 当节点因为持续发送错误进入 `Bus-Off`
- 如果 `AutoBusOff = ENABLE`
- 控制器会按 CAN 协议规定的恢复时机自动退出 `Bus-Off`
- 软件不需要为了“离开 Bus-Off”而主动 `Stop/Start`

反过来，如果 `AutoBusOff = DISABLE`：

- 节点进入 `Bus-Off` 后不会自动恢复
- 软件必须自行决定是否 `Stop/Start` 或重新初始化
- 恢复路径更复杂，也更容易让 M3 日志口径失真

## 5. 建议结论

M3 第一版建议冻结为：

- `AutoBusOff = ENABLE`
- `AutoRetransmission = ENABLE`
- 默认不采用手动 `HAL_CAN_Stop()` / `HAL_CAN_Start()` 作为常规恢复手段
- 只有 `Bus-Off` 被视为“需要恢复”的故障
- 非 `Bus-Off` 错误一律“计数并留痕，不做干预”

### 5.1 为什么建议开 `AutoBusOff`

- 它最符合当前字段表，只需要观测 `Bus-Off` 的进入和退出即可
- 它让 `can_recovery_cnt` 更接近真实链路恢复，而不是“软件重启过一次 CAN”
- 它能避免把 `ACK`、仲裁丢失、瞬时协议错误误处理成一次软件级恢复
- 对 M3 第一版来说，它比手动恢复更稳、更容易解释日志

### 5.2 为什么不建议默认手动 `Stop/Start`

- `Stop/Start` 会把“错误观测”和“人为干预”混成一件事
- 一般错误可能本来会自行消退，但软件重启会掩盖原始故障形态
- 当前字段表没有区分“硬件自动恢复”和“软件重启恢复”，贸然启用会污染 `can_recovery_cnt`

因此，`Stop/Start` 在 M3 第一版中的定位应是：

- 不是默认路径
- 不是常规错误处理动作
- 只保留为后续实验或兜底策略候选项

## 6. recovery 的正式定义

本项目中，`recovery` 建议正式定义为：

- 系统此前已经进入过一次 `Bus-Off`
- 随后第一次观察到该 `Bus-Off` 状态结束
- CAN 外设重新处于可继续正常参与总线通信的状态
- 此时记一次 `can_recovery_cnt += 1`

下列情况不算 recovery：

- `EWG` 消失
- `EPV` 消失
- 某次 `ACK` 错误后下一帧发送成功
- 仲裁丢失后下一帧重新仲裁成功
- 软件主动调用一次 `HAL_CAN_Start()`

也就是说，`recovery` 只对应 `Bus-Off episode` 的闭环，不对应一般错误波动。

## 7. 哪些错误只计数不干预

建议以下错误全部归入“只计数、不干预”：

- `HAL_CAN_ERROR_EWG`
- `HAL_CAN_ERROR_EPV`
- `HAL_CAN_ERROR_STF`
- `HAL_CAN_ERROR_FOR`
- `HAL_CAN_ERROR_ACK`
- `HAL_CAN_ERROR_BR`
- `HAL_CAN_ERROR_BD`
- `HAL_CAN_ERROR_CRC`
- `HAL_CAN_ERROR_TX_ALST0`
- `HAL_CAN_ERROR_TX_ALST1`
- `HAL_CAN_ERROR_TX_ALST2`
- `HAL_CAN_ERROR_TX_TERR0`
- `HAL_CAN_ERROR_TX_TERR1`
- `HAL_CAN_ERROR_TX_TERR2`
- `HAL_CAN_ERROR_RX_FOV0`
- `HAL_CAN_ERROR_RX_FOV1`

统一处理口径建议为：

- `can_error_irq_cnt++`
- 刷新 `can_last_error_code`
- 不调用 `HAL_CAN_Stop()`
- 不调用 `HAL_CAN_Start()`
- 不增加 `can_recovery_cnt`

其中有两个点需要特别说明：

- `TX_ALSTx` 是仲裁丢失。对共享总线来说，这是冲突仲裁结果，不等于需要恢复的链路故障。
- `ACK` 错误通常很有诊断价值，但它更适合暴露“对端缺席/总线闭合问题”，不适合被软件重启掩盖。

## 8. 唯一触发恢复逻辑的错误

M3 第一版建议只有以下条件进入恢复路径：

- `HAL_CAN_ERROR_BOF`

对应口径：

- 第一次进入 `Bus-Off`：`can_bus_off_cnt++`
- 同时刷新 `can_last_error_code`
- 后续若错误中断重复报告仍处于 `Bus-Off`，不重复增加 `can_bus_off_cnt`
- 第一次观察到 `Bus-Off` 已结束：`can_recovery_cnt++`

这套口径要求把“进入 `Bus-Off`”和“仍在 `Bus-Off`”区分开，避免重复记账。

## 9. 错误状态机小表

| 当前状态 | 触发条件 | 记录动作 | 干预动作 | 下一个状态 |
| --- | --- | --- | --- | --- |
| `CAN_OK` | 出现非 `BOF` 错误 | `can_error_irq_cnt++`，刷新 `can_last_error_code` | 无 | `CAN_OK` / `CAN_WARN` / `CAN_PASSIVE` |
| `CAN_WARN` | 再次出现非 `BOF` 错误 | `can_error_irq_cnt++`，刷新 `can_last_error_code` | 无 | `CAN_WARN` / `CAN_PASSIVE` / `CAN_OK` |
| `CAN_PASSIVE` | 再次出现非 `BOF` 错误 | `can_error_irq_cnt++`，刷新 `can_last_error_code` | 无 | `CAN_PASSIVE` / `CAN_OK` |
| `CAN_OK` / `CAN_WARN` / `CAN_PASSIVE` | 首次进入 `BOF` | `can_error_irq_cnt++`，刷新 `can_last_error_code`，`can_bus_off_cnt++` | 无，等待自动恢复 | `CAN_BUS_OFF` |
| `CAN_BUS_OFF` | 仍然处于 `BOF` | 刷新 `can_last_error_code` | 无 | `CAN_BUS_OFF` |
| `CAN_BUS_OFF` | 首次观察到 `BOF` 已清除 | `can_recovery_cnt++`，刷新 `can_last_error_code` | 无 | `CAN_OK` |

说明：

- `CAN_WARN` 和 `CAN_PASSIVE` 主要用于语义理解，不强制要求后续代码中必须做成枚举状态机
- 对 M3 来说，真正必须闭环统计的是 `Bus-Off` 进入和恢复
- 当前代码采用的就是这种“最小状态机实现”
  - 没有单独定义 `CAN_OK / CAN_WARN / CAN_PASSIVE` 枚举变量
  - 只通过 `can_bus_off_latched` 显式区分“当前是否处于 `Bus-Off`”

## 10. 与字段表的逐项对应

| 字段 | 策略对应关系 |
| --- | --- |
| `can_last_error_code` | 每次错误回调或状态刷新时，记录最近一次 `HAL_CAN_GetError()` 返回值 |
| `can_error_irq_cnt` | 每次进入 `HAL_CAN_ErrorCallback()` 时累计 |
| `can_bus_off_cnt` | 每次首次进入 `Bus-Off` episode 时累计 |
| `can_recovery_cnt` | 每次首次退出 `Bus-Off` episode 时累计 |

这 4 个字段共同回答的问题是：

- 是否发生过 CAN 错误
- 最近一次错误是什么
- 是否真的进入过总线级故障
- 是否真的从总线级故障恢复过

## 11. 当前边界

本页冻结 M3 第一版策略，并与当前 ACK fault recovery 板级证据保持一致：

- `HAL_CAN_ActivateNotification()` 已接入，但只覆盖本页定义的最小错误通知集
- `HAL_CAN_ErrorCallback()` 已接入
- `can_last_error_code`、`can_error_irq_cnt`、`can_bus_off_cnt`、`can_recovery_cnt` 已落地到代码
- 这些字段已经进入 `DiagLogTask` 的 M3 CSV 输出
- 当前代码没有实现显式的 `CAN_WARN` / `CAN_PASSIVE` 枚举状态变量
- 已有 ACK fault -> recovery 板级实测样例，证明 ACK 异常下错误计数增长、恢复后成功发送重新增长且错误计数停止增长
- 当前故障注入方式未触发 `Bus-Off`；`Bus-Off -> recovery` 保留为后续更强故障注入边界，不作为 M3 当前收口阻塞项

## 12. 下一步建议

后续建议在保持本页策略不变的前提下，将 `Bus-Off` 作为专项增强验证，而不是 M3 收口阻塞项：

- 如需证明 `Bus-Off -> recovery`，补充更强故障注入方式
- 如需更细诊断，补充 ESR/TEC/REC 原始状态观测
- 当前 M3 的“ACK 故障和恢复行为”已经可回溯
