# MCU 代码逻辑

更新时间：2026-04-20

本文按代码执行路径说明 MCU 侧逻辑，重点是 FreeRTOS 任务、共享数据和 CAN/诊断链路。

## 1. 启动顺序

`main()` 的顺序很标准：

1. `HAL_Init()`
2. `SystemClock_Config()`
3. 初始化外设：
   - GPIO
   - DMA
   - TIM1
   - TIM2
   - USART2
   - USART3
   - CAN1
4. `MX_FREERTOS_Init()`
5. `osKernelStart()`

真正的业务启动主要在 `MX_FREERTOS_Init()` 里完成，而不是 `main()` 的 while 循环里。

## 2. 外设职责

| 外设 | 文件 | 当前用途 |
| --- | --- | --- |
| USART2 | `Core/Src/usart.c` | LiDAR 输入，115200，DMA + IDLE |
| USART3 | `Core/Src/usart.c` | 诊断日志输出，115200 |
| TIM1 CH1 | `Core/Src/tim.c` | 电机 PWM，ARR=999，输出引脚 PE9 |
| TIM2 | `Core/Src/tim.c` | 编码器模式，PA0/PA1 |
| TIM6 | `Core/Src/stm32f4xx_hal_timebase_tim.c` | HAL tick，同时 1 MHz counter 用于 `micros_now()` |
| CAN1 | `Core/Src/can.c` | 点云数据发送，Normal 模式，AutoBusOff 开 |
| GPIO PC0/PC1 | `Core/Src/gpio.c` + `motor.h` | 电机方向 |
| GPIO PC2 | `Core/Src/freertos.c` | 初始化时拉高，推测是驱动使能或外设使能 |

## 3. FreeRTOS 初始化

`MX_FREERTOS_Init()` 里先创建两个队列：

```c
lidarChunkQueue = xQueueCreate(4, sizeof(LidarChunk));
lidarPointQueue = xQueueCreate(16, sizeof(lidar_point_t));
```

然后启动外设：

- 启动 USART2 ReceiveToIdle DMA
- 启动 TIM1 PWM
- 启动 TIM2 encoder
- PC2 拉高
- 启动 CAN1
- 开启 CAN error / bus-off / LEC 等通知

最后创建 5 个任务。

## 4. 任务表

| 任务 | 优先级 | 栈 | 职责 |
| --- | --- | --- | --- |
| `StartDefaultTask` | Normal | 128 | 每 1 ms 调 `CAN_DiagPoll()`，处理 bus-off 恢复统计 |
| `LidarParseTask1` | High | 1024 | 从 chunk 队列取数据，拼接 `parser_buffer`，调用 `luna_input()` |
| `MotorCtrlTask1` | Normal | 128 | 50 ms 周期测速、PID、换向、PWM 输出 |
| `CanTxTask1` | Normal | 512 | 从点队列取 `lidar_point_t`，通过 CAN 双帧发送 |
| `DiagLogTask1` | BelowNormal | 512 | 每秒通过 UART3 输出诊断 CSV |

`LidarParseTask1` 是 High，说明当前设计上优先保证串口数据解析，避免 parser 堵塞。

## 5. 共享数据模型

### 5.1 点结构

`lidar_point_t` 当前字段：

```c
typedef struct {
    uint32_t t_sample_us;
    uint16_t angle_tick;
    float angle_deg;
    uint16_t distance_cm;
    uint8_t quality;
    uint8_t status;
    float tmp;
} lidar_point_t;
```

正式对外字段不包含 `tmp`，`tmp` 目前是 MCU 内部保留字段。

### 5.2 Chunk 结构

`LidarChunk` 当前字段：

```c
typedef struct {
    uint8_t data[64];
    volatile uint16_t count;
    volatile uint8_t ready;
    volatile uint32_t luna_chunk_rx_time_us;
    volatile uint16_t luna_rx_encoder_tick16;
    volatile int32_t luna_rx_encoder_count32;
} LidarChunk;
```

它的作用不是点结构，而是“一个 UART DMA chunk 的原始数据 + 到达时刻 + 到达时刻编码器快照”。

## 6. UART ISR 到解析任务

`HAL_UARTEx_RxEventCallback()` 是数据链路的第一段业务代码。

它只处理 `huart2`：

- 记录 `chunk_time_us`
- 读取 TIM2 编码器 `enc16`
- 维护连续编码器 `enc32`
- 把 DMA buffer 复制进 `LidarChunk`
- `xQueueSendFromISR()` 送入 `lidarChunkQueue`
- 统计队列高水位或 drop
- 重启 ReceiveToIdle DMA

ISR 内不解析 LiDAR 帧，这点很重要。解析被放到 FreeRTOS 任务里做，避免 ISR 过长。

## 7. 解析任务

`LidarParseTask1` 做的是流式拼帧：

1. 从 `lidarChunkQueue` 阻塞取 chunk。
2. 把 chunk 追加到 `parser_buffer[64]`。
3. 记录本 chunk 在 buffer 中的起始位置 `chunk_start_index`。
4. 调 `luna_input()`。
5. 根据 `luna_input()` 返回的已消费字节数，把剩余 bytes 前移。
6. 如果 buffer 溢出，`parser_overflow_cnt++` 并清空。

这里的 `chunk_start_index` 很关键，因为 `luna_input()` 需要知道一个帧是否属于当前 chunk，才能基于当前 chunk 的时间/编码器锚点回推。

## 8. LiDAR 解析和过滤

`luna_input()` 当前负责消费 `parser_buffer` 中的连续字节流，并结合当前 `local_chunk` 的时间/编码器锚点生成 `lidar_point_t`。协议常量集中在 `Core/Inc/luna_protocol.h`，避免在解析逻辑里散落裸数字。

TF-Luna 帧规则：

- 帧长：`LUNA_FRAME_LEN = 9`
- 帧头：`LUNA_HEADER_0 / LUNA_HEADER_1`，即 `0x59 0x59`
- checksum：前 `LUNA_CHECKSUM_LEN` 字节累加，与 `LUNA_CHECKSUM_INDEX` 字节比较
- 字段下标：距离、强度、温度分别使用 `LUNA_DISTANCE_*`、`LUNA_AMP_*`、`LUNA_TEMP_*`

`luna_input()` 内部当前拆分为：

- `luna_is_frame_header()`：判断当前 index 是否为帧头
- `luna_checksum_ok()`：校验当前 9 字节候选帧
- `luna_decode_raw_frame()`：解码 `distance_cm`、`amp`、`tmp`
- `luna_raw_frame_valid()`：执行强度和距离过滤
- `luna_estimate_pose()`：根据 chunk 锚点、速度和编码器计数估算 `t_sample_us` 与 `angle_tick`
- `luna_make_point()`：生成 `lidar_point_t`
- `luna_publish_point()`：发送到 `lidarPointQueue`

过滤与重同步规则：

| 条件 | 动作 |
| --- | --- |
| 非帧头字节 | 跳过 1 字节，`luna_header_skip_cnt++` |
| checksum 错 | 不输出点，`checksum_fail_cnt++`、`luna_resync_cnt++`，并滑动 1 字节继续找帧头 |
| `amp < LUNA_MIN_AMP` 或 `amp == LUNA_INVALID_AMP` | 不输出点，`amp_low_cnt++` |
| `distance_cm < LUNA_MIN_DISTANCE_CM` | 不输出点，`too_near_cnt++` |
| 点队列满 | `lidar_point_drop_cnt++` |
| 成功入点队列 | `luna_frame_ok_cnt++`，并维护 `lidar_point_q_hwm` |

成功点会写入：

- `t_sample_us`
- `angle_tick`
- `angle_deg`
- `distance_cm`
- `quality`
- `status`
- `tmp`

当前实现已经具备滑动重同步，并已引入显式 `LunaParseState` parser 状态机。`luna_input()` 的主循环通过 `SEARCH_HEADER -> VERIFY_FRAME -> DECODE_FRAME -> OUTPUT_POINT` 拆分处理路径，让帧搜索、校验、解码、过滤和发布边界更清楚。
## 9. CAN 发送

`CanTxTask1` 只做一件事：取点，调用 `LIDAR_SendCAN()`。

`LIDAR_SendCAN()` 每个点发两帧：

### 0x123

```text
byte0 seq
byte1 distance_cm high
byte2 distance_cm low
byte3 angle_deg float bits[31:24]
byte4 angle_deg float bits[23:16]
byte5 angle_deg float bits[15:8]
byte6 angle_deg float bits[7:0]
byte7 quality
```

### 0x124

```text
byte0 seq
byte1 t_sample_us[31:24]
byte2 t_sample_us[23:16]
byte3 t_sample_us[15:8]
byte4 t_sample_us[7:0]
byte5 angle_tick high
byte6 angle_tick low
byte7 status
```

发送失败统计分两层：

- `can_tx_fail_frame_cnt`：`HAL_CAN_AddTxMessage()` 某一帧失败
- `can_tx_fail_point_cnt`：点发送函数返回失败

成功点统计：

- `can_tx_ok_point_cnt`

## 10. CAN 错误统计

CAN 初始化打开了 AutoBusOff 和错误通知。

`HAL_CAN_ErrorCallback()`：

- `can_error_irq_cnt++`
- 保存 `can_last_error_code`
- 如果检测到 bus-off 且未 latch，则 `can_bus_off_cnt++`

`CAN_DiagPoll()`：

- 在默认任务里每 1 ms 调用
- 如果之前 bus-off latch，且 ESR 里 BOFF 已清除，则 `can_recovery_cnt++`

这构成 M3 诊断链路的 CAN 错误统计基础。

## 11. 诊断日志

`DiagLogTask1` 每秒通过 UART3 发一行 CSV。

当前字段覆盖：

- tick
- chunk 队列深度和高水位
- UART chunk drop / oversize
- parser overflow
- checksum / amp_low / too_near
- point 队列深度和高水位
- point drop
- CAN tx ok / fail
- CAN frame fail
- CAN last error / error irq / bus-off / recovery

这个任务是后续 M5 长稳测试必须依赖的观测出口。

## 12. 代码里的几个注意点

- `main.c` 目前是已修改状态，新增文档前不要把它当成干净基线。
- `status` 当前主要打 `LIDAR_STATUS_ESTIMATED`，异常帧本身不会通过 CAN 出去。
- `g_speed_valid` 由电机任务根据连续测速有效性置位；速度无效时，LiDAR 角度估算走退化路径。
- CAN 协议中 float 上总线对跨语言解析要求高，Linux 侧用 `struct.unpack(">f", ...)` 匹配大端解析。
- `seq` 是 `uint8_t`，回绕规则需要在协议正文继续补清楚。
