# M3 CAN ACK fault -> recovery 板级实测记录

## 1. 结论

M3 已完成 CAN ACK fault -> recovery 板级实测。

本次故障注入方式下，断开/异常状态会触发 ACK Error、Error Warning 和 Error Passive，表现为 `can_tx_fail_point_cnt`、`can_tx_fail_frame_cnt` 与 `can_error_irq_cnt` 持续增长。恢复总线后，`can_tx_ok_point_cnt` 重新增长，错误计数停止增长。

本次未触发 `Bus-Off`：`can_bus_off_cnt=0`，`can_recovery_cnt=0`。因此 `Bus-Off -> recovery` 不作为 M3 当前收尾证据，保留为边界说明。

## 2. 证据文件

- `docs/m3/data/diag_m3_ack_fault_recovery_excerpt.csv`

## 3. 字段判读

重点看每行最后 7 个字段：

```text
can_tx_ok_point_cnt,
can_tx_fail_point_cnt,
can_tx_fail_frame_cnt,
can_last_error_code,
can_error_irq_cnt,
can_bus_off_cnt,
can_recovery_cnt
```

## 4. 恢复段

摘录：

```text
522090,...,3552,48870,48870,0x00200023,1867497,0,0
529132,...,4260,48870,48870,0x00200023,1867497,0,0
```

判读：

- `can_tx_ok_point_cnt` 从 `3552` 增加到 `4260`
- `can_tx_fail_point_cnt` 保持 `48870`
- `can_tx_fail_frame_cnt` 保持 `48870`
- `can_error_irq_cnt` 保持 `1867497`

这说明恢复段内 CAN 点云发送重新成功，错误计数停止增长。

## 5. 故障段

摘录：

```text
531144,...,4335,48997,48997,0x00200023,1872423,0,0
548246,...,4335,50716,50716,0x00200023,1938710,0,0
```

判读：

- `can_tx_ok_point_cnt` 基本停在 `4335`
- `can_tx_fail_point_cnt` 从 `48997` 增加到 `50716`
- `can_tx_fail_frame_cnt` 从 `48997` 增加到 `50716`
- `can_error_irq_cnt` 从 `1872423` 增加到 `1938710`

这说明异常状态下 CAN 发送失败和错误中断持续增长。

## 6. 再次恢复段

摘录：

```text
551264,...,4365,50990,50990,0x00200023,1949121,0,0
561324,...,5376,50990,50990,0x00200023,1949121,0,0
```

判读：

- `can_tx_ok_point_cnt` 从 `4365` 增加到 `5376`
- `can_tx_fail_point_cnt` 保持 `50990`
- `can_tx_fail_frame_cnt` 保持 `50990`
- `can_error_irq_cnt` 保持 `1949121`

这说明总线恢复后，成功发送重新增长，故障计数停止增长。

## 7. 错误码边界

本次主要错误码为：

```text
0x00200023
```

它至少包含：

- `0x00000001`：`HAL_CAN_ERROR_EWG`
- `0x00000002`：`HAL_CAN_ERROR_EPV`
- `0x00000020`：`HAL_CAN_ERROR_ACK`
- `0x00200000`：`HAL_CAN_ERROR_PARAM`

本次未包含：

- `0x00000004`：`HAL_CAN_ERROR_BOF`

所以本次证据证明的是 ACK fault recovery，不证明 Bus-Off recovery。
