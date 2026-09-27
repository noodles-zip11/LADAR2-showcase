# M1 采集与异常证据补齐

## 1. 结论

本轮 M1 已补齐“有样例和日志可证明完成”的核心证据链，当前仓库内已归档：

- LiDAR 原始帧 debug 样例
- Linux 接收终端截图
- `candump` 抓包日志与截图
- Linux 接收端 CSV
- `too_near` 真实异常样例
- 调试记录与错误记录

本轮异常补齐以真实 `too_near` 样例和非零 `status=0x08` 样例为主；`checksum_fail` / 错帧未在本轮单独专项采集。

## 2. 归档目录

### 截图

- `docs/m1/assets/lidar_raw_chunk_debug.png`
- `docs/m1/assets/lidar_raw_bytes_debug.png`
- `docs/m1/assets/linux_receiver_terminal.png`
- `docs/m1/assets/candump_capture.png`
- `docs/m1/assets/too_near_debug.png`

### 数据与日志

- `docs/m1/data/can_distance_20260326_164322.csv`
- `docs/m1/data/candump_normal.log`

### 过程记录

- `docs/debug_notes.md`
- `docs/error_journal.md`

## 3. 证据说明

### 3.1 LiDAR 原始帧样例

原始帧截图：

- `docs/m1/assets/lidar_raw_chunk_debug.png`
- `docs/m1/assets/lidar_raw_bytes_debug.png`

关键字节样例：

```text
59 59 4F 00 4A 26 F2 09 6C
```

解释：

- `59 59`：帧头
- `4F 00`：距离 `0x004F = 79 cm`
- `4A 26`：幅值原始量
- `F2 09`：温度相关原始量
- `6C`：校验字节

这说明 MCU 已经在 UART 回调里收到并缓存了 LiDAR 原始 9 字节帧。

### 3.2 CAN 与 Linux 接收链路样例

相关文件：

- `docs/m1/assets/candump_capture.png`
- `docs/m1/assets/linux_receiver_terminal.png`
- `docs/m1/data/candump_normal.log`
- `docs/m1/data/can_distance_20260326_164322.csv`

日志概况：

- `candump_normal.log` 共 `8206` 行
- 其中 `0x123` 报文 `4103` 条
- 其中 `0x124` 报文 `4103` 条
- `can_distance_20260326_164322.csv` 共 `5638` 行
- CSV 时间范围：`2026-03-26T16:43:22.505` 到 `2026-03-26T16:44:19.261`
- CSV 中 `status=8` 共 `5638` 行

`candump` 片段：

```text
(1774515057.611741) can0 123#60004742B8E5E0FF
(1774515057.611771) can0 124#6006E0F3C005E608
(1774515057.621460) can0 123#61004742B76DB7FF
(1774515057.621779) can0 124#6106E11AA405DA08
(1774515057.631327) can0 123#62004742B6343FFF
(1774515057.631659) can0 124#6206E1416B05D008
```

CSV 片段：

```text
host_time,elapsed_s,seq,distance_cm,angle_deg,quality,t_sample_us,angle_tick,status
2026-03-26T16:43:22.505,0.067,239,69,17.632652,255,110306184,288,8
2026-03-26T16:43:22.507,0.069,240,69,16.959185,255,110316135,277,8
2026-03-26T16:43:22.508,0.069,241,69,16.224489,255,110326103,265,8
2026-03-26T16:43:22.508,0.070,242,69,15.551020,255,110336049,254,8
2026-03-26T16:43:22.509,0.070,243,69,14.816327,255,110346018,242,8
```

这说明 CAN 双帧发送、Linux 接收重组、CSV 落盘和 GUI 显示链路都已跑通。

### 3.3 异常样例

异常截图：

- `docs/m1/assets/too_near_debug.png`

异常证据：

```text
too_near_cnt = 1
distance = 14
```

解释：

- 当前代码在 `distance < 28` 时进入 `too_near_cnt++` 分支
- 本轮 debug 已抓到 `distance = 14 cm`
- 同时 `too_near_cnt` 已增至 `1`

因此，本轮已经补到一条真实异常样例，证明“过近帧被识别并计数丢弃”。

### 3.4 非零状态码样例

Linux 接收终端与 CSV 中都出现：

```text
status=0x08
```

结合当前代码语义，可作为 `LIDAR_STATUS_ESTIMATED` 的非零状态码样例。

## 4. 与 M1 任务的对应关系

- [x] 采集 LiDAR 原始数据样例并存档
  - 证据：`lidar_raw_chunk_debug.png`、`lidar_raw_bytes_debug.png`
- [x] 补异常状态样例
  - 证据：`too_near_debug.png`、CSV/终端中的 `status=0x08`
- [x] 整理 M1 的原始采集截图、日志和数据片段
  - 证据：`docs/m1/assets/`、`docs/m1/data/`
- [x] 将调试过程填入 `docs/debug_notes.md`
- [x] 将真实错误条目填入 `docs/error_journal.md`

## 5. 当前实现补充

M1 的原始证据仍然有效，但当前 MCU 解析实现已经比当时更完善：

- TF-Luna 帧格式相关常量已集中到 `Core/Inc/luna_protocol.h`
- `luna_input()` 已拆分为帧头判断、checksum 校验、原始帧解码、质量过滤、时间/角度估算、点生成和队列发布
- `luna_input()` 主循环已引入显式 `LunaParseState` 状态机，状态包括帧头搜索、帧校验、帧解码和点输出
- checksum 失败后当前采用滑动 1 字节重同步策略，不输出点，并累加 `checksum_fail_cnt` 与 `luna_resync_cnt`
- 非帧头字节会跳过 1 字节，并累加 `luna_header_skip_cnt`
- 成功入点队列会累加 `luna_frame_ok_cnt`
- `too_near` 和低幅值过滤规则仍保持为只计数、不输出点

这些属于 MCU 内部解析硬化，不改变 M1 已归档的 CAN 双帧样例、CSV 字段和上位机重组语义。
## 5. 备注

- 本轮 M1 以真实采集证据补齐为主，没有额外为了“凑覆盖率”伪造或推测异常样例。
- 如果后续需要更强的异常覆盖，可以在 M2/M3 前追加 `checksum_fail_cnt` / 错帧专项采集，并继续归档到 `docs/m1/`。
