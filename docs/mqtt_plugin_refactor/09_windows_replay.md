# Windows 回放与 live CAN 测试入口

这个文件说明 Windows 端怎么做不上板验证，以及怎么在有 Windows CAN 适配器时跑 `live CAN + MQTT`。

## 1. 默认回放模式

Windows 上最稳的入口仍然是回放模式：

```powershell
python can_recv4_windows.py
```

默认行为：

- 使用 `docs/m4/data/can_distance_v2_sample.csv`
- 以 `replay` 模式启动 UI
- 默认关闭 MQTT，避免没有 broker 时干扰 UI 测试
- 不连接真实 CAN，不修改 MCU/CAN 协议

指定自己的 CSV：

```powershell
python can_recv4_windows.py --input-csv docs\m4\data\can_distance_20260329_145239.csv
```

如果要同时测试 MQTT：

```powershell
python can_recv4_windows.py --mqtt
```

## 2. Windows live CAN 模式

Windows 没有 Linux 的 `can0` 设备。要跑 live CAN，必须通过 `python-can` 的 Windows backend，例如：

- `virtual`：无硬件自检用
- `gs_usb`：candleLight/cantact/gs_usb 固件类 USB-CAN 适配器
- `pcan`：PEAK PCAN 适配器
- `kvaser`：Kvaser 适配器
- `vector`：Vector 适配器
- `slcan`：串口 CAN 适配器

无硬件验证 live 输入链路：

```powershell
python can_recv4_windows.py --mode live --can-interface virtual --channel ladar2_virtual
```

PCAN 示例：

```powershell
python can_recv4_windows.py --mode live --can-interface pcan --channel PCAN_USBBUS1 --bitrate 500000 --mqtt
```

candleLight 示例：

```powershell
python can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000 --mqtt
```

2026-05-09 已用该路径完成 Windows 上板最小闭环验证：candleLight USB-CAN + `gs_usb` + local Mosquitto，真实 CAN live 点持续进入，`lidar/01/telemetry` 以 `mode=live` 发布，`lidar/01/cmd` 的 `ping` 命令被程序处理并返回 `result=OK` 日志，正常关闭时发布 `status offline`。完整记录见 [10_m6_5_windows_board_mqtt.md](./10_m6_5_windows_board_mqtt.md)。

先不启动 UI，只探测 CAN 帧：

```powershell
python tools\can_probe_windows.py --seconds 30 --parse
```

不要用 `python -m can.logger -i gs_usb ...` 作为 candleLight 的首选探测命令。它不会加载本项目在 `can_input.py` 中设置的 `libusb-package` backend，容易在 Windows 上报 `usb.core.NoBackendError: No backend available`。

SLCAN 示例：

```powershell
python can_recv4_windows.py --mode live --can-interface slcan --channel COM3 --bitrate 500000 --mqtt
```

真实适配器需要先安装对应驱动，并确认 `python-can` 支持对应 backend。candleLight/gs_usb 还需要 Python 依赖 `pyusb`。

## 3. 查看等价主程序命令

```powershell
python can_recv4_windows.py --mode live --can-interface virtual --channel ladar2_virtual --print-command
```

会打印等价的 `can_recv4.py` 参数，方便复制到主程序排查。

## 4. 当前边界

- Windows replay/UI/core/output/MQTT 合同可以不上板测试。
- Windows live CAN 的代码路径已经开放到 `python-can` backend。
- `virtual` backend 只能证明软件路径能打开总线，不能证明真实 CAN 适配器和 MCU 链路正常。
- 真实 live CAN + MQTT 最小闭环已在 Windows + candleLight `gs_usb` + local Mosquitto 下验证通过；broker 断开韧性也已用临时 broker 端口 `1884` 验证通过。
- 真实硬件派生告警已验证通过：遮挡/近距离场景下可观察到 `lidar/01/alarm`，包括 `derived_too_near`、`derived_no_valid_points` 和 `derived_near_obstacle`；telemetry 同时继续周期发布是预期行为。
- 串口输入仍是 reserved stub，不代表真实串口链路已经完成。
