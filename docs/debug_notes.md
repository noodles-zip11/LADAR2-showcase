# 调试记录

这份文档给你手动记录每次调试过程，供自动化读取。

建议写法：
- 只写这次真实做过的事，不猜测、不补脑。
- 命令、现象、错误原文尽量保留。
- 每次调试新增一个小节，按时间顺序往下写。

---

## 2026-03-21 00:00

### 本次目标
- 

### 涉及文件或模块
- 

### 本次改动
- 

### 使用的命令
```bash
# 例：
# cmake --preset Debug
# cmake --build --preset Debug
```

### 观察到的现象
- 

### 错误或异常
- 原文：
- 发生条件：

### 初步判断
- 

### 已确认有效的做法
- 

### 仍未解决的问题
- 

### 下次继续时建议先看什么
- 

---

## 2026-03-26 M1 采集与调试

### 本次目标
- 补齐 M1 所需的原始采集证据、异常样例、Linux 接收日志和截图。
- 确认为什么调试时会反复停在 `Error_Handler()`，避免影响后续抓原始帧与异常样例。

### 涉及文件或模块
- `Core/Src/main.c`
- `Core/Src/luna.c`
- `docs/error_journal.md`
- `LOCAL_USER_HOME\Desktop\DevEnv\DevEnv\stm32f1_stlink.cfg`
- Linux 接收端 CSV / `candump` 日志 / GUI

### 本次改动
- 调整 CLion/OpenOCD 调试配置，修正 ST-Link 启动时的复位行为。
- 外部调试脚本最终改为：
```tcl
source [find interface/stlink.cfg]
transport select hla_swd
source [find target/stm32f4x.cfg]
reset_config srst_nogate connect_assert_srst

$_TARGETNAME configure -rtos FreeRTOS
```
- 将 M1 采集得到的截图、日志、CSV 复制进仓库 `docs/m1/` 目录归档。

### 使用的命令
```bash
# Linux 侧
candump can0 > candump_normal.log

# GDB / CLion 调试时实际查看的关键命令
p/x (RCC->CFGR & RCC_CFGR_SWS)
p/x RCC->PLLCFGR
info registers pc
```

### 观察到的现象
- Linux 接收端能稳定输出 `seq / distance_cm / angle_deg / quality / t_sample_us / angle_tick / status`。
- GUI 能实时画出距离曲线，并生成 `can_distance_20260326_164322.csv`。
- `candump` 能稳定看到 `0x123` 与 `0x124` 成对出现。
- 通过 debug 在 `HAL_UARTEx_RxEventCallback` 中看到了 LiDAR 原始帧头 `0x59 0x59`。
- 通过 debug 在 `luna.c` 的 `too_near_cnt++` 路径捕获到 `distance = 14`、`too_near_cnt = 1` 的真实异常样例。

### 错误或异常
- 原文：
  - 调试启动后反复停在 `Error_Handler()`
  - OpenOCD 还曾报过：`invalid command name "connect_assert_srst"`
- 发生条件：
  - 在 CLion 中启动 OpenOCD debug，会话未执行干净复位时
  - 将 `connect_assert_srst` 误写成单独命令而不是 `reset_config` 参数时

### 初步判断
- 一开始误以为是 `SystemClock_Config()` 或时钟参数本身写错。
- 后续通过 Call Stack、PC、RCC 寄存器确认，真正问题是调试启动复位不干净，RCC 保留了旧的 PLL 运行状态，不是时钟参数本身非法。

### 已确认有效的做法
- 用 Call Stack + `PC` 判断是否“真停”在 `Error_Handler()`。
- 用 `p/x (RCC->CFGR & RCC_CFGR_SWS)` 判断进入 `SystemClock_Config()` 前系统时钟是否已经是 PLL。
- 将 OpenOCD 脚本改成 `reset_config srst_nogate connect_assert_srst` 后，debug 恢复正常。
- 原始帧抓取时看 callback 局部变量 `chunk.data` / `chunk.count`，不要再盯旧的 `chunk1/chunk2`。

### 仍未解决的问题
- 本轮 M1 采集中没有额外单独复现 `checksum_fail_cnt` 或错帧样例，当前异常证据以 `too_near` 和非零 `status=0x08` 为主。

### 下次继续时建议先看什么
- 先看 `docs/m1/README.md` 中的证据索引，确认当前已归档样例和缺口。
- 如果要补更强的异常覆盖，优先专项采 `checksum_fail_cnt` / 错帧，再追加到 `docs/m1/`。
