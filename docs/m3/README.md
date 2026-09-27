# M3 CAN 与诊断闭环

## 文档索引

- `README.md`
- `02_DiagLogTask字段表.md`
- `03_CAN错误模型与恢复策略.md`
- `04_联调与抓包记录.md`
- `05_错误统计与恢复样例.md`
- `06_DiagLogTask样例.md`
- `07_ACK故障恢复实测记录.md`

## 1. 当前结论

截至 2026-03-29，M3 已经完成了以下部分：

- MCU 侧统计埋点已经落地
- `DiagLogTask` 已切换为 M3 CSV 输出
- Linux 侧最小重组闭环已经跑通
- 已归档一轮正常链路抓包和 Linux 重组产物
- 已归档一段 MCU 故障态 `DiagLogTask` 样例
- 已归档一段 MCU 正常态 `DiagLogTask` 样例

当前 M3 按第一阶段收口口径已经完成：

- CAN ACK fault -> recovery 板级实测已完成
- `Bus-Off` 未在当前故障注入方式下触发，作为边界说明保留

也就是说，当前状态更准确地说是：

- 代码侧：MCU 已完成，Linux 最小重组已完成
- 证据侧：正常链路已有 Linux 与 MCU 样例，故障态与 ACK fault recovery 样例也已归档
- 协议侧：CAN 帧定义、Linux 双帧重组、50ms 超时、覆盖统计和 `seq` 256 回绕规则已冻结
- 验证侧：ACK 故障与恢复行为已有板级实测证据

## 2. 已落实能力

### 2.1 MCU 侧

- `seq` 固定为 `uint8_t`，双帧共用同一个序号
- `can_tx_ok_point_cnt`
- `can_tx_fail_point_cnt`
- `can_tx_fail_frame_cnt`
- `lidar_chunk_q_hwm`
- `lidar_point_q_hwm`
- `can_last_error_code`
- `can_error_irq_cnt`
- `can_bus_off_cnt`
- `can_recovery_cnt`
- `DiagLogTask` 已按 M3 字段表输出 CSV

### 2.2 Linux 侧

- 按 `seq` 重组 `0x123` / `0x124`
- `50 ms` 双帧超时淘汰
- 同 `seq` 同类型帧覆盖计数
- 输出 Linux 重组 CSV
- 输出最小重组统计摘要

## MCU LiDAR 解析硬化记录

当前 `Core/Src/luna.c` 已完成内部模块拆分、解析硬化和显式 parser 状态机收口，目标是提高可维护性、重同步能力和可观测性，同时保持现有数据链路、点结构和 CAN 输出协议不变。

本轮代码边界如下：

- `luna.h` 只保留模块公共接口：
  - `luna_input()`
  - `LIDAR_STATUS_*`
- `luna_protocol.h` 集中保存 TF-Luna 协议常量：
  - 帧头：`LUNA_HEADER_0 / LUNA_HEADER_1`
  - 帧长与校验：`LUNA_FRAME_LEN`、`LUNA_CHECKSUM_LEN`、`LUNA_CHECKSUM_INDEX`
  - 字段下标：`LUNA_DISTANCE_*`、`LUNA_AMP_*`、`LUNA_TEMP_*`
  - 过滤阈值：`LUNA_MIN_AMP`、`LUNA_INVALID_AMP`、`LUNA_MIN_DISTANCE_CM`
- `luna.c` 内部保留私有结构：
  - `LunaRawFrame`：承载 TF-Luna 原始帧解码结果，例如 `distance_cm`、`amp`、`tmp`
  - `LunaPoseEstimate`：承载时间与角度估算结果，例如 `t_sample_us`、`angle_tick`、`status`
  - `LunaParseState`：承载 parser 内部状态，例如帧头搜索、帧校验、帧解码和点输出
- `luna_input()` 内部职责拆分为：
  - 帧头判断
  - checksum 校验
  - 原始帧解码
  - 质量过滤
  - 时间与角度估算
  - `lidar_point_t` 生成
  - 点队列发布

当前解析行为如下：

- 非帧头字节：跳过 1 字节，并累加 `luna_header_skip_cnt`
- checksum 错误：不输出点，累加 `checksum_fail_cnt` 和 `luna_resync_cnt`，并滑动 1 字节继续重同步
- `amp < LUNA_MIN_AMP` 或 `amp == LUNA_INVALID_AMP`：不输出点，并累加 `amp_low_cnt`
- `distance_cm < LUNA_MIN_DISTANCE_CM`：不输出点，并累加 `too_near_cnt`
- 成功入点队列：累加 `luna_frame_ok_cnt`

本轮不改变以下外部协议和链路：

- TF-Luna 输入仍为 9 字节帧，帧头 `0x59 0x59`
- checksum 仍为前 8 字节累加，与第 9 字节比较
- `lidar_point_t` 字段语义不变
- CAN `0x123 / 0x124` 双帧输出协议不变
- `parser_buffer`、`local_chunk`、`chunk_start_index` 的数据链路不变

当前已引入显式 `LunaParseState` parser 状态机，状态包括：

- `LUNA_PARSE_SEARCH_HEADER`：扫描帧头，非帧头字节累加 `luna_header_skip_cnt`
- `LUNA_PARSE_VERIFY_FRAME`：校验候选 9 字节帧，checksum 错误时累加 `checksum_fail_cnt` 和 `luna_resync_cnt`，并滑动 1 字节重同步
- `LUNA_PARSE_DECODE_FRAME`：解码原始帧并执行强度、距离过滤
- `LUNA_PARSE_OUTPUT_POINT`：估算时间/角度，生成 `lidar_point_t` 并发布到点队列

这属于内部 parser 结构升级，不改变 TF-Luna 输入 wire format、`lidar_point_t` 字段语义或 CAN `0x123 / 0x124` 输出协议。后续如继续推进工业级协议，应优先补充上板长稳验证、异常注入样例和更多 byte stream parser 测试。

## MCU LiDAR 协议成熟度判断

按当前代码状态，LiDAR 解析链路已经从“能用的业务代码”推进到“接近工程化的协议 parser”：

- 公共接口与私有实现已经分离，`luna.h` 只保留 `luna_input()` 和 `LIDAR_STATUS_*`
- TF-Luna 帧格式、字段下标、checksum 下标和过滤阈值已经集中到 `luna_protocol.h`
- `luna_input()` 已按 `LunaParseState` 拆成帧头搜索、帧校验、帧解码和点输出
- checksum 错误具备滑动 1 字节重同步，不再只按固定 9 字节盲跳
- 非帧头、重同步、成功入队、低幅值、过近、点队列满等路径都有计数器
- 对外 TF-Luna 输入、`lidar_point_t` 字段语义和 CAN 双帧协议保持不变

当前还不能直接宣称“工业级完全闭环”，主要缺口不是 parser 结构或 CAN 接收端规则，而是验证证据：

- 需要上板长稳验证 parser 计数器是否长期稳定
- 需要补充噪声、错 checksum、半帧、连续帧、buffer 边界等异常流测试证据
- 需要决定是否把 `luna_header_skip_cnt`、`luna_resync_cnt`、`luna_frame_ok_cnt` 纳入正式诊断 CSV
- `Bus-Off` 未在当前 ACK 故障注入方式下触发，作为后续更强故障注入边界保留
## 3. 当前归档产物

当前仓库中已经归档的 M3 数据文件包括：

- `docs/m3/data/candump_m3_normal.log`
- `docs/m3/data/can_distance_20260328_215800.csv`
- `docs/m3/data/can_distance_20260328_215800_summary.txt`
- `docs/m3/data/diag_m3_normal.csv`
- `docs/m3/data/diag_m3_fault_20260328_excerpt.csv`
- `docs/m3/data/diag_m3_ack_fault_recovery_excerpt.csv`

这些文件分别对应：

- 原始 CAN 总线抓包
- Linux 侧重组后的点级 CSV
- Linux 侧重组统计摘要
- MCU 侧正常态 `DiagLogTask` 样例
- MCU 侧故障态 `DiagLogTask` 片段
- MCU 侧 ACK fault -> recovery 板级实测片段

## 4. 收口证据

### 4.1 ACK fault -> recovery 板级实测

M3 已完成 CAN ACK fault -> recovery 板级实测：

- 断开/异常状态下 `can_tx_fail_point_cnt` 与 `can_error_irq_cnt` 持续增长
- 恢复后 `can_tx_ok_point_cnt` 重新增长，错误计数停止增长
- `Bus-Off` 未在当前故障注入方式下触发，作为边界说明保留

证据见：

- `docs/m3/data/diag_m3_ack_fault_recovery_excerpt.csv`
- `docs/m3/07_ACK故障恢复实测记录.md`

### 4.2 已回写的协议正文

M3 第一项要求“冻结 CAN 帧定义、字节序、缩放规则和丢帧重组规则”。当前已写回：

- Linux 侧 `50 ms` 双帧超时规则
- 同 `seq` 同类型帧覆盖统计规则
- `seq` 的 `255 -> 0` 正常回绕规则

## 5. 当前边界

- 当前 M3 收尾证据采用 ACK fault -> recovery，不宣称 Bus-Off recovery。
- `can_bus_off_cnt` 与 `can_recovery_cnt` 字段仍保留在诊断 CSV 中，用于后续更强故障注入测试。
- 若后续必须证明 Bus-Off，需要增加更强故障注入方式或补充 ESR/TEC/REC 原始状态观测，不作为 M3 当前收口阻塞项。
