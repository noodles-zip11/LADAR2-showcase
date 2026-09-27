# M7 演示视频脚本

目标时长：1 到 3 分钟。

## 1. 录制前检查

- 如果录实时模式，先给雷达板上电并连接 CAN 适配器。
- 上位机 Python 依赖已经安装。
- 回放 CSV 存在：`docs/m4/data/can_distance_v2_sample.csv`。
- 终端字体调大，确保录屏里能看清命令。
- 尽量把终端和 UI 放在同一屏，方便展示“命令启动 -> 点云显示”。

如果现场硬件不方便，就录回放模式，并明确说明这是历史采集数据的回放。

## 2. 推荐回放演示命令

Windows：

```powershell
py -3 .\can_recv4_windows.py --mode replay --input-csv .\docs\m4\data\can_distance_v2_sample.csv
```

Linux：

```bash
python3 can_recv4.py --mode replay --input-csv docs/m4/data/can_distance_v2_sample.csv
```

## 3. 可选实时演示命令

Windows candleLight/gs_usb：

```powershell
py -3 .\can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000
```

Linux SocketCAN：

```bash
python3 can_recv4.py --mode live --channel can0
```

## 4. 90 秒旁白稿

先展示 UI 或终端：

> 这是 LADAR2，一个基于 STM32F407、TF-Luna、编码器电机、CAN 和 Python 上位机的旋转式 2D LiDAR 感知系统。

展示回放/实时命令：

> MCU 把每个点拆成两帧 CAN 报文，`0x123` 和 `0x124`。上位机按序号配对，写入固定 CSV 格式，并渲染成点云。

展示点云界面：

> 同一套上位机工具同时支持实时接收和 CSV 回放，所以现场采集的数据可以离线复盘、调试和分析。

展示 README 或 M7 总览：

> 项目按 milestone 组织。M3 是 CAN 诊断，M4 是上位机接收显示闭环，M5 是长稳基线，M6 是几何质量分析。

展示 M5/M6 指标片段：

> 当前证据包括约 1 小时 42 分钟的长稳基线，重组 `612466` 个点，CAN 重组丢包率 `0.001143%`。几何分析里，墙面直线 RMSE 是 `7.44 mm`，盒子重复性 p95 是 `20.00 mm`。

最后说明边界：

> V1 阶段暂时不把云端和 AI 作为核心交付，重点是把本地感知链路、字段契约、时间戳语义、回放、诊断和验证边界做清楚。

## 5. 画面安排

| 时间 | 画面 | 说明 |
| --- | --- | --- |
| 0-15 s | README 或 M7 总览 | 说明项目目标和主链路 |
| 15-40 s | 终端命令 + UI | 展示可复现运行 |
| 40-65 s | 点云 UI | 展示实际输出 |
| 65-85 s | `docs/spec_freeze/03_报文表.md` | 说明 CAN 双帧设计 |
| 85-110 s | M5/M6 指标 | 展示验证结果 |
| 110-130 s | M7 边界说明 | 说明 V1 范围纪律 |

## 6. 视频证据边界

脚本已经准备好，但视频文件需要你手动录制。建议输出路径：

```text
docs/m7/assets/m7_demo_video.mp4
```

录完后建议在这里补一句记录：

- 录制日期
- live 还是 replay
- 使用的命令
- 画面中展示了哪些证据

