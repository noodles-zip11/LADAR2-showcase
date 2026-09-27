# M3 DiagLogTask 样例

## 1. 当前状态

截至 2026-03-29，`DiagLogTask` 已切换为 M3 CSV 结构，当前已经归档的样例有：

- 正常态样例：`docs/m3/data/diag_m3_normal.csv`
- 故障态片段：`docs/m3/data/diag_m3_fault_20260328_excerpt.csv`

当前仍待补的样例有：

- 无 M3 当前收口阻塞样例；Bus-Off recovery 保留为后续更强故障注入边界

## 2. 当前 M3 Header

说明：当前代码中存在 `luna_header_skip_cnt`、`luna_resync_cnt`、`luna_frame_ok_cnt` 三个 MCU 内部解析诊断计数器，并已由 `LunaParseState` parser 状态机路径维护；但本页归档的 M3 CSV header 尚未包含它们。该样例仍用于验证既有 M3 DiagLogTask 字段顺序。

```text
tick_ms,lidar_chunk_q_depth,lidar_chunk_q_hwm,uart_chunk_drop_cnt,uart_chunk_oversize_cnt,parser_overflow_cnt,checksum_fail_cnt,amp_low_cnt,too_near_cnt,lidar_point_q_depth,lidar_point_q_hwm,lidar_point_drop_cnt,can_tx_ok_point_cnt,can_tx_fail_point_cnt,can_tx_fail_frame_cnt,can_last_error_code,can_error_irq_cnt,can_bus_off_cnt,can_recovery_cnt
```
## 3. 已归档样例

文件：

- `docs/m3/data/diag_m3_normal.csv`
- `docs/m3/data/diag_m3_fault_20260328_excerpt.csv`
- `docs/m3/data/diag_m3_ack_fault_recovery_excerpt.csv`

片段：

```text
24128,0,1,0,0,0,0,0,3,0,1,0,2378,0,0,0x00000000,0,0,0
25133,0,1,0,0,0,0,0,3,0,1,0,2478,0,0,0x00000000,0,0,0
26137,0,1,0,0,0,0,0,3,0,1,0,2579,0,0,0x00000000,0,0,0

190070,0,1,0,0,0,0,8,21,0,1,0,5576,13430,13430,0x00200063,503636,0,0
191076,0,1,0,0,0,0,8,21,0,1,0,5576,13531,13531,0x00200063,507418,0,0
192082,0,1,0,0,0,0,8,21,0,1,0,5576,13632,13632,0x00200063,511200,0,0
```

## 4. 样例说明

这份样例已经能够说明：

- `DiagLogTask` 的字段顺序和 `02_DiagLogTask字段表.md` 一致
- 队列高水位、解析计数、CAN 发送计数、错误计数都能被输出
- `can_last_error_code` 已按十六进制输出
- 正常态下 `can_tx_fail_point_cnt=0`
- 正常态下 `can_last_error_code=0x00000000`

ACK fault recovery 样例还能说明：

- 故障段 `can_tx_fail_point_cnt`、`can_tx_fail_frame_cnt`、`can_error_irq_cnt` 持续增长
- 恢复段 `can_tx_ok_point_cnt` 重新增长，错误计数停止增长

本次样例不说明：

- `can_recovery_cnt` 在 Bus-Off 恢复后增加

## 5. 当前边界

M3 当前收口采用 ACK fault -> recovery 证据。`can_bus_off_cnt` 与 `can_recovery_cnt` 仍保留为后续 Bus-Off 专项测试字段，但不作为当前 M3 收口阻塞项。
