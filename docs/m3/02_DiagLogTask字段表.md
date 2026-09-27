# M3 DiagLogTask 字段表

## 1. 目标

冻结 `DiagLogTask` 的最小 CSV 字段集，明确：

- 字段名
- 字段含义
- 字段来源
- 更新时机
- 单位
- 是否累计计数

本页只冻结字段口径，不涉及代码实现。

## 2. 设计原则

- `DiagLogTask` 从 M2 电机稳速日志切换为 M3 链路诊断日志
- 日志按固定周期输出，建议周期为 `1000 ms`
- 计数类字段统一采用“上电后累计值”
- 快照类字段只记录当前状态，不做累计
- 队列字段同时保留“当前深度”和“历史高水位”

## 3. 建议 CSV Header

```text
tick_ms,lidar_chunk_q_depth,lidar_chunk_q_hwm,uart_chunk_drop_cnt,uart_chunk_oversize_cnt,parser_overflow_cnt,checksum_fail_cnt,amp_low_cnt,too_near_cnt,lidar_point_q_depth,lidar_point_q_hwm,lidar_point_drop_cnt,can_tx_ok_point_cnt,can_tx_fail_point_cnt,can_tx_fail_frame_cnt,can_last_error_code,can_error_irq_cnt,can_bus_off_cnt,can_recovery_cnt
```

## 4. 字段表

| 字段 | 含义 | 来源 | 更新时机 | 单位 | 是否累计 |
| --- | --- | --- | --- | --- | --- |
| `tick_ms` | 本条诊断日志输出时刻 | `HAL_GetTick()` | 每次 `DiagLogTask` 输出时采样 | ms | 否 |
| `lidar_chunk_q_depth` | `lidarChunkQueue` 当前深度 | `uxQueueMessagesWaiting(lidarChunkQueue)` | 每次 `DiagLogTask` 输出时采样 | 个 | 否 |
| `lidar_chunk_q_hwm` | `lidarChunkQueue` 启动以来最大深度 | `lidarChunkQueue` 高水位统计 | 队列深度创新高时更新，日志输出时采样 | 个 | 是，峰值型 |
| `uart_chunk_drop_cnt` | UART chunk 入队失败次数 | `HAL_UARTEx_RxEventCallback()` | `xQueueSendFromISR()` 失败时累计 | 次 | 是 |
| `uart_chunk_oversize_cnt` | DMA chunk 超出缓冲大小次数 | `HAL_UARTEx_RxEventCallback()` | `Size > sizeof(chunk.data)` 时累计 | 次 | 是 |
| `parser_overflow_cnt` | parser 缓冲溢出次数 | `LidarParseTask1()` | `parser_buffer` 放不下新 chunk 时累计 | 次 | 是 |
| `checksum_fail_cnt` | LiDAR 校验失败次数 | `luna_input()` | 校验失败时累计 | 次 | 是 |
| `amp_low_cnt` | 幅值过低或无效次数 | `luna_input()` | `amp` 不满足条件时累计 | 次 | 是 |
| `too_near_cnt` | 过近帧次数 | `luna_input()` | `distance < 28` 时累计 | 次 | 是 |
| `lidar_point_q_depth` | `lidarPointQueue` 当前深度 | `uxQueueMessagesWaiting(lidarPointQueue)` | 每次 `DiagLogTask` 输出时采样 | 个 | 否 |
| `lidar_point_q_hwm` | `lidarPointQueue` 启动以来最大深度 | `lidarPointQueue` 高水位统计 | 队列深度创新高时更新，日志输出时采样 | 个 | 是，峰值型 |
| `lidar_point_drop_cnt` | 点入队失败次数 | `luna_input()` | `xQueueSend(lidarPointQueue, ...)` 失败时累计 | 次 | 是 |
| `can_tx_ok_point_cnt` | 成功调用 `LIDAR_SendCAN()` 的点数 | `CanTxTask1()` | `LIDAR_SendCAN() == HAL_OK` 时累计 | 点 | 是 |
| `can_tx_fail_point_cnt` | 发送失败的点数 | `CanTxTask1()` | `LIDAR_SendCAN() != HAL_OK` 时累计 | 点 | 是 |
| `can_tx_fail_frame_cnt` | `HAL_CAN_AddTxMessage()` 失败的帧数 | `LIDAR_SendCAN()` | 任一帧 `HAL_CAN_AddTxMessage()` 失败时累计 | 帧 | 是 |
| `can_last_error_code` | 最近一次 CAN 错误码 | 后续来自 `HAL_CAN_GetError()` | 错误状态刷新时更新，日志输出时采样 | bitmask/hex | 否 |
| `can_error_irq_cnt` | CAN 错误回调进入次数 | 后续 `HAL_CAN_ErrorCallback()` | 每次错误回调时累计 | 次 | 是 |
| `can_bus_off_cnt` | 进入 Bus-Off 的次数 | 后续 CAN 错误处理路径 | 每次检测到 Bus-Off 进入时累计 | 次 | 是 |
| `can_recovery_cnt` | 从 Bus-Off 恢复的次数 | 后续恢复逻辑 | 每次恢复完成时累计 | 次 | 是 |

## 5. 字段分组解释

### 5.1 UART chunk 入口层

- `lidar_chunk_q_depth`
- `lidar_chunk_q_hwm`
- `uart_chunk_drop_cnt`
- `uart_chunk_oversize_cnt`
- `parser_overflow_cnt`

这一组用于判断：

- UART 中断回调是否来得及把 chunk 推进队列
- parser 是否开始积压

### 5.2 LiDAR 数据过滤层

- `checksum_fail_cnt`
- `amp_low_cnt`
- `too_near_cnt`

这一组用于区分：

- 输入链路本身的原始帧异常
- 业务过滤导致的正常丢弃

这组不属于 CAN 发送失败。
当前代码另有 3 个 MCU 内部解析诊断计数器：

- `luna_header_skip_cnt`：非帧头字节跳过次数
- `luna_resync_cnt`：checksum 失败后滑动重同步次数
- `luna_frame_ok_cnt`：成功入点队列的点数

这些计数器由 `luna_input()` 的显式 `LunaParseState` parser 状态机路径维护。它们当前不属于 M3 DiagLogTask CSV header，不进入 CAN，不改变正式点结构。若后续要进入诊断 CSV，需要单独升级 header、样例和字段表。

### 5.3 点队列与 CAN 发送层

- `lidar_point_q_depth`
- `lidar_point_q_hwm`
- `lidar_point_drop_cnt`
- `can_tx_ok_point_cnt`
- `can_tx_fail_point_cnt`
- `can_tx_fail_frame_cnt`

这一组用于回答：

- 点有没有在 MCU 内部排队堵住
- 点是否已经推进到 CAN 发送阶段
- 点级失败和帧级失败是否一致

### 5.4 总线错误层

- `can_last_error_code`
- `can_error_irq_cnt`
- `can_bus_off_cnt`
- `can_recovery_cnt`

这一组当前先冻结字段，不要求本步立即实现。

冻结这些字段的原因是后续真正接入总线错误统计时，不需要再改 CSV 结构。

## 6. 当前实现状态

本页首先冻结字段口径；截至 2026-03-28，当前代码已经把这些字段真正接入到了 `DiagLogTask` 的 M3 CSV 输出。

当前已落实到代码并进入 `DiagLogTask` 的字段包括：

- `uart_chunk_drop_cnt`
- `uart_chunk_oversize_cnt`
- `parser_overflow_cnt`
- `checksum_fail_cnt`
- `amp_low_cnt`
- `too_near_cnt`
- `lidar_point_drop_cnt`
- `lidar_chunk_q_hwm`
- `lidar_point_q_hwm`
- `can_tx_ok_point_cnt`
- `can_tx_fail_point_cnt`
- `can_tx_fail_frame_cnt`
- `can_last_error_code`
- `can_error_irq_cnt`
- `can_bus_off_cnt`
- `can_recovery_cnt`
- `lidar_chunk_q_depth`
- `lidar_point_q_depth`

当前已经具备的样例有：

- Linux 正常链路重组样例：`docs/m3/data/can_distance_20260328_215800.csv`
- Linux 重组统计摘要：`docs/m3/data/can_distance_20260328_215800_summary.txt`
- MCU 正常态 `DiagLogTask` 样例：`docs/m3/data/diag_m3_normal.csv`
- MCU 故障态 `DiagLogTask` 片段：`docs/m3/data/diag_m3_fault_20260328_excerpt.csv`
- MCU ACK fault -> recovery 片段：`docs/m3/data/diag_m3_ack_fault_recovery_excerpt.csv`

当前 M3 收口不再阻塞于 Bus-Off recovery 样例；Bus-Off 专项测试保留为后续边界。

## 7. 当前边界

当前不再需要继续改造 `DiagLogTask` 结构。M3 收口采用 ACK fault -> recovery 证据：

- 故障段：`can_tx_fail_point_cnt` 与 `can_error_irq_cnt` 持续增长
- 恢复段：`can_tx_ok_point_cnt` 重新增长，错误计数停止增长
- `Bus-Off` 未在当前故障注入方式下触发，作为后续更强故障注入边界保留
