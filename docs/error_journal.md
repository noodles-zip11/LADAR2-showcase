# 错误处理记录

这份文档用于记录你遇到过的真实错误，供自动化总结排查规律。

建议写法：
- 错误信息尽量贴原文。
- 如果还没解决，也照样记下来。
- 一次错误单独开一个小节，后续补充也放在原处。

---

## 错误条目 1

### 错误原文
```text
调试时程序反复停在 Error_Handler()
Call Stack:
Reset_Handler -> main -> SystemClock_Config -> Error_Handler

GDB:
(gdb) p/x (RCC->CFGR & RCC_CFGR_SWS)
$1 = 0x8

(gdb) p/x RCC->PLLCFGR
$2 = 0x8012008
```

### 出现场景
- 什么时候发生：在 CLion 中启动 OpenOCD 调试会话时
- 哪个命令触发：下载并运行 / Debug `LADAR2`
- 影响了什么：程序在启动阶段进入 `Error_Handler()`，无法继续正常进入主逻辑，导致无法稳定做串口与 LiDAR 调试

### 初步原因
- 不是运行时 LiDAR / CAN 逻辑出错，而是启动阶段 `SystemClock_Config()` 调用 `HAL_RCC_OscConfig()` 失败。
- 调试时进入 `SystemClock_Config()` 前，`RCC->CFGR & RCC_CFGR_SWS == 0x8`，说明系统时钟已经是 PLL，而不是干净复位后的 HSI 默认状态。
- 当前 `SystemInit()` 没有主动把 RCC 恢复到默认状态；如果调试启动没有做完整系统复位，RCC 会保留上一次运行的时钟状态，导致 `HAL_RCC_OscConfig()` 因“PLL 已在用且配置不一致”返回错误。
- 当前 CLion OpenOCD 运行配置中还使用了自定义脚本，脚本内含 `reset_config none`，增加了调试启动复位不干净的风险。

### 已做过的排查
- 在 CLion 中查看 Call Stack，确认调用链为：
  - `Reset_Handler -> main -> SystemClock_Config -> Error_Handler`
- 在 GDB 中查看 PC，确认停在 `Error_Handler+10`
- 在 GDB 中检查 RCC 状态：
  - `RCC->CFGR & RCC_CFGR_SWS == 0x8`
  - `RCC->PLLCFGR == 0x8012008`
- 核对代码后确认失败点位于 `HAL_RCC_OscConfig(&RCC_OscInitStruct)` 返回非 `HAL_OK`
- 核对 CLion 工作区配置，发现 OpenOCD 配置使用：
  - `reset-type="INIT"`
  - 自定义板卡脚本 `LOCAL_USER_HOME\\Desktop\\DevEnv\\DevEnv\\stm32f1_stlink.cfg`
- 核对该脚本内容，确认其实际引用 `target/stm32f4x.cfg`，但又额外设置了 `reset_config none`

### 解决方法或绕过办法
- 初始临时绕过办法是先断电重上电，再启动调试，避免沿用上一次运行残留的 RCC 状态。
- 最初误判为 `SystemClock_Config()` 或时钟参数本身有问题，后续通过 Call Stack、PC 和 RCC 寄存器排查，确认根因在调试启动复位不干净。
- 最终修复方式：
  - 修改 `LOCAL_USER_HOME\\Desktop\\DevEnv\\DevEnv\\stm32f1_stlink.cfg`
  - 使用 `transport select hla_swd`
  - 使用 `reset_config srst_nogate connect_assert_srst`
  - CLion 中保持 OpenOCD 下载方式为“始终”，重置方式改为更强的调试复位路径
- 如果后续仍偶发复现，再考虑在代码里增加更稳妥的时钟初始化兜底逻辑。

### 当前状态
- 已解决

### 备注
- 相关代码位置：
  - `Core/Src/main.c:208`
  - `Core/Src/main.c:210`
  - `Core/Src/main.c:295`
  - `Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c`
- 外部调试配置位置：
  - `LOCAL_USER_HOME\\Desktop\\DevEnv\\DevEnv\\stm32f1_stlink.cfg`

---

## 错误条目 2

### 错误原文
```text
Error: invalid command name "connect_assert_srst"
```

### 出现场景
- 什么时候发生：修正 OpenOCD reset 配置时
- 哪个命令触发：在 CLion 中重新启动 OpenOCD debug 会话
- 影响了什么：OpenOCD 初始化失败，调试会话无法启动

### 初步原因
- 将 `connect_assert_srst` 误写成了单独命令。
- OpenOCD 中它应作为 `reset_config` 的参数，而不是独立语句。

### 已做过的排查
- 查看 OpenOCD 报错堆栈，确认错误定位到 `stm32f1_stlink.cfg`
- 核对 OpenOCD 配置语法后，确认正确写法应为：
  - `reset_config srst_nogate connect_assert_srst`

### 解决方法或绕过办法
- 将错误写法改为单行 `reset_config srst_nogate connect_assert_srst`

### 当前状态
- 已解决

### 备注
- 该错误属于调试脚本语法错误，不是 MCU 固件问题
