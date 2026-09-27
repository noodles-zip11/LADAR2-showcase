# M4 Linux Agent Guide

本文件用于给后续开发者或代码代理一个统一入口。

后续默认规则是：

- 当前 Linux 侧 `接收 -> 解析 -> 存储 -> 回放 -> 2D 点云显示` 一律归入 `M4`
- `docs/m4/` 是正式主目录

## 1. Source of Truth

优先级从高到低如下：

1. `docs/m4/README.md`
2. `docs/spec_freeze/01_规格冻结页.md`
3. `docs/spec_freeze/02_字段表.md`
4. `docs/spec_freeze/03_报文表.md`
5. `docs/spec_freeze/04_时间戳说明表.md`
6. `Core/Src/luna.c`
7. `Core/Src/can.c`
8. `Core/Inc/main.h`
9. `Core/Inc/luna.h`
10. `can_recv4.py`

如果文档与代码冲突，先核对 `docs/spec_freeze/` 和 `docs/m4/README.md`，再回看实现是否未同步。

## 2. M4 范围

M4 当前负责的不是 MCU 采样算法，而是 Linux 闭环交付：

- 实时接收 `can0`
- 解码 `0x123 / 0x124`
- 按 `seq` 做双帧重组
- 输出正式 CSV
- 回放新旧 CSV
- 显示 XY 2D 点云

M4 不负责：

- 改 MCU 发包协议
- 改 MCU 采样/配对/零位逻辑
- 改 TF-Luna 原始串口协议

## 3. Frozen MCU Contract

Linux 端必须严格消费 MCU 已冻结协议，不得自行改义。

### 3.1 正式点字段

MCU 正式点字段为：

- `t_sample_us`
- `angle_tick`
- `angle_deg`
- `distance_cm`
- `quality`
- `status`

其中：

- `distance_cm` 是正式距离字段，不引入新的 `distance_mm`
- `angle_tick` 是原始量
- `angle_deg` 是派生量，但当前仍通过 CAN 正式发送
- `t_sample_us` 是 MCU 侧时间，不是 Linux 接收时间

### 3.2 Linux 正式字段

Linux 正式 CSV 固定为 9 列：

1. `host_rx_time_us`
2. `t_sample_us`
3. `angle_tick`
4. `angle_deg`
5. `distance_cm`
6. `x_mm`
7. `y_mm`
8. `quality`
9. `status`

补充说明：

- `seq` 只作为运行时调试字段存在，不进入正式 CSV
- `x_mm / y_mm` 由 `distance_cm + angle_deg` 推导
- Linux 不做角度镜像、不做几何纠偏、不补造 MCU 没发出的异常点

### 3.3 时间戳语义

- `t_sample_us`：MCU 侧点采样时间
- `host_rx_time_us`：Linux 完成点重组时记录的主机时间

禁止把 `host_rx_time_us` 当作测量时间，也禁止把 `t_sample_us` 改写成主机时间。

### 3.4 CAN 协议

当前 MCU 发两帧标准 CAN：

- `0x123`：`seq + distance_cm + angle_deg(float bits) + quality`
- `0x124`：`seq + t_sample_us + angle_tick + status`

规则：

- 标准帧
- DLC = 8
- 多字节整数按大端
- `angle_deg` 按 IEEE754 `float` 位模式解码
- 两帧通过 1 字节 `seq` 配对

默认不修改这套协议。

## 4. 四层拆分

### 4.1 接收层

职责：

- 从 Linux `can0` 读入原始 CAN 报文
- 为实时模式提供稳定输入
- 为回放模式提供统一点流入口

允许修改：

- CLI 参数
- 启动方式
- Linux 错误提示
- 无 GUI / 离线模式扩展

不允许修改：

- 协议字段语义
- 时间戳定义

### 4.2 协议层

职责：

- 识别 `0x123 / 0x124`
- 解码字段
- 按 `seq` 重组
- 处理超时、覆盖、残帧统计

当前实现关键约束：

- 保持 CAN ID 不变
- 保持大端解码
- 保持 `angle_deg` 浮点位模式解码
- 保持 50 ms 重组超时

### 4.3 存储层

职责：

- 把重组后的点稳定写入正式 CSV
- 固定表头、单位和兼容策略
- 生成 `_summary.txt`

要求：

- 正式 CSV 只写 9 列
- 旧调试 CSV 只做兼容回放，不再作为正式输出格式

### 4.4 可视化层

职责：

- 提供单页双模式界面
- 中央主画布显示 XY 2D 点云
- 顶部显示状态条
- 右侧显示控制面板
- 回放模式显示时间轴

要求：

- 主视图必须是 XY 2D 点云，不再是距离-时间曲线
- 历史点默认保留为压暗背景点
- 最近一圈扫描需要单独提取，并支持按段组织显示
- 最近一圈默认以连续轮廓线叠加显示，提升当前轮廓可读性
- 实时与回放共用一套 `LidarPoint` 数据流和一套渲染逻辑

## 5. 当前实现对象

`can_recv4.py` 当前内部对象固定为：

- `LidarPoint`
- `CanPointAssembler`
- `CsvPointWriter`
- `CsvReplaySource`
- `PointCloudWindow`

CLI 参数固定为：

- `--mode live|replay`
- `--channel can0`
- `--input-csv <path>`
- `--save-csv <path>`
- `--replay-speed 0.5|1|2`

## 6. M4 收尾检查项

每次做 M4 相关改动后，至少核对以下项：

1. `0x123 / 0x124` 解码无回归
2. `seq` 256 回绕不崩溃
3. 50 ms 超时统计仍正确
4. 正式 CSV 表头未漂移
5. 旧版 `docs/m1` 与 `docs/m3` 样例仍能回放
6. 主界面仍是 XY 2D 点云
7. 文档中统一使用 `M4 Linux 闭环`

## 7. 命名规则

后续在本仓库内写文档、提交说明、截图标题时，统一使用：

- `M4 Linux 闭环`
