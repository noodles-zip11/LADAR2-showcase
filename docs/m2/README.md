# M2 电机稳速与同步收口

## 1. 结论

M2 当前已经切换为“单圈换向”的双向扫描策略，并完成了本轮版本的主要交付：

- 电机已从“仅编码器测速”升级为“双向闭环稳速 + 周期换向”
- 已输出目标转速与实际转速对比日志
- 已补齐启动段、稳态段、换向段曲线
- 已形成正式的距离-角度配对策略说明
- 已完成非机械项的角度同步误差预算

当前延期项：

- 机械误差实测值，转入 M6 几何质量与重复性测试，不作为 M6 前冻结阻塞项

## 2. 本轮交付物

- [01 Steady Validation](./01_稳速验证.md)
- [02 Pairing Strategy](./02_距离角度配对策略.md)
- [03 Sync Error Budget](./03_角度同步误差预算.md)
- [data/m2_bidirectional_reverse_log.csv](./data/m2_bidirectional_reverse_log.csv)

### 图像

- ![Overview](assets/m2_bidirectional_overview.png)
- ![Negative steady](assets/m2_negative_steady_zoom.png)
- ![Positive steady](assets/m2_positive_steady_zoom.png)
- ![Reverse transition](assets/m2_reverse_transition.png)

## 3. 当前版本对应关系

### 3.1 闭环稳速控制

已完成。当前版本不是固定单方向转动，而是：

- 每转一圈后进入停转/换向过程
- 速度降到阈值以下后翻转方向
- 再按斜坡恢复到目标速度

### 3.2 目标转速与实际转速对比

已完成。当前已有：

- MCU 串口 CSV
- 总览曲线
- 正向/反向稳态放大图
- 换向段放大图

### 3.3 启动、稳态、长稳与换向

已完成当前轮的证据整理：

- 启动/恢复段：由换向过程图和目标斜坡恢复图给出
- 正向稳态：有独立放大图与统计
- 反向稳态：有独立放大图与统计
- 周期换向：有总览图与换向段图

### 3.4 距离-角度配对策略正式说明

已完成，见：

- [02 Pairing Strategy](./02_距离角度配对策略.md)

### 3.5 误差预算

已完成三项：

- 编码器分辨率
- 配对时刻误差
- 转速波动误差

机械误差延期到 M6 实测，见：

- [03 Sync Error Budget](./03_角度同步误差预算.md)

## 4. 当前 LiDAR 解析实现补充

M2 的距离-角度配对公式仍然成立；当前代码只是把 TF-Luna 解析层做了内部硬化：

- 帧长、字段下标、checksum 下标和过滤阈值集中到 `luna_protocol.h`
- checksum 失败后采用滑动 1 字节重同步，减少错位后连续丢帧的风险
- 新增 `luna_header_skip_cnt`、`luna_resync_cnt`、`luna_frame_ok_cnt` 作为 MCU 内部解析诊断计数器
- 已引入显式 `LunaParseState` parser 状态机，当前状态包括 `SEARCH_HEADER`、`VERIFY_FRAME`、`DECODE_FRAME`、`OUTPUT_POINT`

这些改动不改变 `t_sample_us`、`angle_tick`、`angle_deg`、`distance_cm` 的输出语义。
## 4. 当前状态

按“M6 前冻结非机械误差预算，机械误差转入 M6 几何质量测试”的口径，M2 可以视为 M6 前冻结。
