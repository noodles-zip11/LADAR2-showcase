# M6.5 Windows 上板 MQTT 验证记录

> Date: 2026-05-10
> Scope: Windows host + candleLight USB-CAN + local Mosquitto + live radar board
> Result: live CAN + MQTT board loop PASS; broker-disconnect resilience PASS; derived hardware alarm PASS

## 1. Purpose

本记录用于补齐 M6.5 原先留到上板的 MQTT 验证项：在 Windows 端直接使用真实 CAN 适配器和雷达板，不切换到 Linux，验证 `live CAN -> can_recv4_windows.py -> MQTT telemetry/cmd/status` 的最小闭环。

## 2. Environment

| Item | Value |
| --- | --- |
| Host OS | Windows |
| CAN adapter | candleLight USB to CAN adapter |
| python-can backend | `gs_usb` |
| CAN channel | `0` |
| Bitrate | `500000` |
| Broker | local Mosquitto on `localhost:1883` |
| MQTT topics observed | `lidar/01/status`, `lidar/01/telemetry`, `lidar/01/alarm`, `lidar/01/cmd` |

PCAN was not used. The first attempt with `--can-interface pcan --channel PCAN_USBBUS1` failed because `PCANBasic.dll` was not installed. The real Windows adapter was identified as candleLight, so the verified backend is `gs_usb`.

## 3. Commands

Program terminal:

```powershell
python can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000 --mqtt
```

MQTT subscriber terminal:

```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h localhost -t "lidar/01/#" -v
```

Command publisher terminal:

```powershell
$tmp = New-TemporaryFile
[System.IO.File]::WriteAllText($tmp.FullName, '{"cmd":"ping","req_id":"board_ping"}', [System.Text.UTF8Encoding]::new($false))
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h localhost -t "lidar/01/cmd" -f $tmp.FullName -q 1
Remove-Item $tmp
```

The temporary-file publish form is required on Windows PowerShell because direct `-m '{"cmd":"ping"}'` can strip JSON quotes before the payload reaches Mosquitto.

## 4. Evidence Summary

| Check | Result | Evidence |
| --- | --- | --- |
| Real live CAN data | PASS | Program log showed increasing `seq` values and live point fields such as `distance=36cm`, `angle=106.59deg` to `119.57deg`, `quality=255`, `t_sample_us=...` |
| MQTT telemetry in live mode | PASS | Subscriber showed repeated `lidar/01/telemetry` payloads with `"mode": "live"`, `point_count` around 800, `min_distance_cm` around 36-38, and `reassembly.ok` increasing |
| MQTT command path | PASS | Program log showed `MQTT cmd: cmd=ping req_id=board_ping result=OK`; subscriber also showed `lidar/01/cmd {"cmd":"ping","req_id":"board_ping"}` |
| Normal shutdown status | PASS | Subscriber showed `lidar/01/status {"device_id":"lidar-01","state":"offline"}` after UI shutdown |
| Broker disconnect resilience | PASS | Temporary Mosquitto broker on port `1884` was stopped and restarted; live CAN/UI continued while broker was down, and MQTT resumed after broker restart |
| Derived hardware alarm trigger | PASS | Physical blocking / near-obstacle testing produced `lidar/01/alarm` with `alarm_source=derived_distance`, `alarm_reason=derived_too_near`, `alarm_source=derived_no_valid_points`, and `alarm_reason=derived_near_obstacle`; telemetry continued in parallel as expected |

## 5. Archived Logs

The following raw logs were copied under `docs/mqtt_plugin_refactor/evidence/`:

- `2026-05-08_windows_selfcheck_and_mqtt_closed_loop.txt`
- `2026-05-08_windows_replay_program_log.txt`
- `2026-05-08_windows_replay_mqtt_sub_log.txt`
- `2026-05-09_windows_replay_cmd_log.txt`
- `2026-05-10_windows_board_derived_alarm_observed.md`

The Windows board screenshots in the conversation provide the live CAN + MQTT visual evidence for this record.

## 6. Checkpoint Decision

Can check off:

- live mode real CAN + MQTT minimum loop
- MQTT telemetry publish in live mode
- MQTT command receive and dispatch (`ping`)
- normal shutdown publishes retained offline status
- live-mode broker disconnect resilience
- derived hardware alarm publication on `lidar/01/alarm`

Removed from this checkpoint:

- long-running hardware stability test: intentionally not part of the current MQTT checkpoint closure

M6.5 MQTT stage is closed for the current scope. MCU-native status-bit alarm remains a protocol capability, but the board-side closure uses gateway-derived alarm semantics because the observed hardware condition reports `latest_status=8` (`STATUS_ESTIMATED`) while still producing valid derived alarm events.
