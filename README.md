# LADAR2 · STM32F407 旋转式 2D LiDAR 嵌入式项目

LADAR2 是一个嵌入式项目：基于 STM32F407、TF-Luna LiDAR、编码器电机与 CAN 总线，配套 Linux/Windows 上位机，实现旋转式 2D LiDAR 数据采集、传输、回放和几何分析。

本仓库是基于源仓库已提交 `main` 文件树重建的脱敏公开快照：不包含原提交历史、分支、PR 或标签；机器本地绝对路径已脱敏。项目源码、文档和验证数据按原快照保留。此次整理没有重新组装或复测硬件，以下验证状态仍以各阶段原有证据为准，不代表新增验证。

## 当前状态

| 阶段 | 状态 | 主要证据 |
| --- | --- | --- |
| M1 原始采集 | 已收口 | `docs/m1/` |
| M2 电机与角度同步 | 非机械误差预算已收口；机械误差仍是边界 | `docs/m2/` |
| M3 CAN 与诊断 | 第一阶段验收口径已收口 | `docs/m3/`、`docs/spec_freeze/03_报文表.md` |
| M4 上位机闭环 | 已收口 | `docs/m4/` |
| M5 长稳基线 | 接受短长稳基线，不宣称严格 4h 通过 | `docs/m5/` |
| M6 几何质量 | 离线几何基线已完成 | `docs/m6/` |
| M6.5 MQTT 插件 | 当前本地/上板 MQTT 范围已收口；云端和 ESP32 不在范围内 | `docs/mqtt_plugin_refactor/` |
| M7 面试交付与 V1 封板 | 文档交付已准备 | `docs/m7/` |

## 主链路

```text
TF-Luna UART
-> STM32 USART2 DMA/IDLE
-> 解析与过滤
-> 时间/角度配对
-> CAN 0x123 + 0x124
-> 上位机双帧重组
-> CSV 存储
-> 回放与 2D 点云显示
```

## 目录结构

| 路径 | 作用 |
| --- | --- |
| `Core/` | STM32 固件源码，基于 CubeMX 生成后扩展 |
| `can_recv4.py` | Linux 上位机主入口：实时接收、回放和 UI |
| `can_recv4_windows.py` | Windows 上板入口，适配 candleLight/gs_usb |
| `can_core.py` | 上位机纯业务计算：XY 转换、状态汇总、告警状态 |
| `can_input.py` | 输入适配层：CSV 回放、实时 CAN、串口预留 stub |
| `can_output.py` | 输出适配层：CSV/log 输出 |
| `can_mqtt.py` | MQTT 输出适配和命令/状态 topic 处理 |
| `tools/` | 自检、M5 长稳、M6 分析、MQTT 闭环脚本 |
| `docs/spec_freeze/` | 字段、CAN 报文、时间戳语义冻结文档 |
| `docs/m1/` 到 `docs/m6/` | 各阶段证据与分析 |
| `docs/mqtt_plugin_refactor/` | M6.5 MQTT 重构与验证记录 |
| `docs/m7/` | V1 面试交付包 |

## 环境准备

安装 Python 依赖：

```powershell
py -3 -m pip install -r .\requirements.txt
```

Windows 上板使用 candleLight/gs_usb 时，需要保持雷达板和 CAN 适配器连接，并使用 `gs_usb` backend。Linux 实时 CAN 需要先在系统侧把 `can0` 拉起。

## 常用命令

Windows 回放 UI：

```powershell
py -3 .\can_recv4_windows.py --mode replay --input-csv .\docs\m4\data\can_distance_v2_sample.csv
```

Linux 回放 UI：

```bash
python3 can_recv4.py --mode replay --input-csv docs/m4/data/can_distance_v2_sample.csv
```

Linux 实时 CAN：

```bash
python3 can_recv4.py --mode live --channel can0
```

Windows 实时 CAN：

```powershell
py -3 .\can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000
```

Windows 实时 CAN + MQTT：

```powershell
py -3 .\can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000 --mqtt
```

运行完整自检（上位机、合同、M8 离线分析骨架、Luna 固件解析器 host harness）：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1
```

重新生成 M6 几何分析：

```powershell
py -3 .\tools\m6_group_analysis.py --run-dir .\docs\m6\runs\m6_manual
py -3 .\tools\m6_tuning_scan.py --run-dir .\docs\m6\runs\m6_manual
```

可选 M5 复测命令：

```powershell
py -3 .\tools\m5_long_run.py --duration-s 14400 --can-interface gs_usb --channel 0 --bitrate 500000
```

当前已接受的 M5 基线约为 1h42min，不是严格 4h 通过。只有在需要更强验收口径时才需要跑上面的复测。

## 协议和数据契约

| 契约 | 文档 |
| --- | --- |
| CSV 与 MCU 点字段 | `docs/spec_freeze/02_字段表.md` |
| CAN `0x123` / `0x124` 报文 | `docs/spec_freeze/03_报文表.md` |
| 时间戳语义 | `docs/spec_freeze/04_时间戳说明表.md` |
| M7 图示和汇总表 | `docs/m7/01_system_diagrams.md` |

正式 CSV 表头：

```text
host_rx_time_us,t_sample_us,angle_tick,angle_deg,distance_cm,x_mm,y_mm,quality,status
```

## 演示路径

面试演示推荐顺序：

1. 打开 `docs/m7/02_project_overview_one_page.md`，讲项目总览。
2. 用 `docs/m4/data/can_distance_v2_sample.csv` 打开回放 UI。
3. 打开 `docs/spec_freeze/03_报文表.md`，说明 CAN 双帧契约。
4. 打开 `docs/m5/05_current_run_summary.md`，说明长稳基线。
5. 打开 `docs/m6/runs/m6_manual/geometry_metrics.md`，说明墙面/盒子几何指标。

1 到 3 分钟演示视频脚本在 `docs/m7/04_demo_video_script.md`。

## 已知边界

- M5 已有短长稳基线，但严格 4h 运行仍是可选/待补项。
- M2 机械误差实测仍是物理测量边界。
- M3 当前采用 ACK fault recovery 作为第一阶段板级证据；完整 Bus-Off 注入保留为后续更强故障测试。
- MQTT 只收口到本地/plugin/上板最小闭环。ESP32、云端上传、TLS/auth、原始点云 MQTT 全量上传都不属于 V1。
- `v1.0.0` 标签属于源仓库；本公开快照不包含原标签或其 Git 历史。
