# M6.5 Verification Record

> **Date**: 2026-05-10
> **Scope**: Linux-side refactor + MQTT plugin; Windows board-side MQTT closure verified
> **Status**: Phase A PASS; Phase B PASS; Phase C PASS (Prompt 13 + 14); Phase D MQTT board loop PASS; broker-disconnect resilience PASS; derived hardware alarm PASS; MQTT stage closed

## 1. Verification Summary

| Phase | Description | Status | Evidence |
|-------|------------|--------|----------|
| A | Code contract closure (no hardware) | **PASS** | `selfcheck_all.ps1` PASS |
| B | Mosquitto + Paho closed loop | **PASS** | `tools/mqtt_closed_loop.ps1` PASS on this machine; tools resolved from `C:\Program Files\mosquitto` |
| C | Documentation + UI evidence | **PASS** | Docs updated; offscreen replay screenshots captured; Prompt 14 local closure verified |
| D | Hardware verification | **PASS for M6.5 MQTT scope** | Windows candleLight `gs_usb` board run verified live CAN + MQTT telemetry/cmd/offline minimum loop; broker-disconnect resilience passed; derived hardware alarm publication observed on `lidar/01/alarm` |

## 2. Phase A — Code Contract Closure

### 2.1 Verification Commands

```powershell
# Individual self-checks
python -m py_compile can_recv4.py can_parser.py can_input.py can_core.py can_output.py can_mqtt.py mqtt_smoke_test.py
python tools/selfcheck_protocol.py
python tools/selfcheck_csv_roundtrip.py
python tools/selfcheck_geometry.py
python tools/selfcheck_fixtures.py
python tools/selfcheck_contract.py
python tools/selfcheck_mqtt_contract.py
python tools/selfcheck_replay_alarm.py
python tools/selfcheck_core.py
python tools/selfcheck_input.py
python tools/selfcheck_output.py

# Full suite
powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1
```

### 2.2 Results

| Check | Result |
|-------|--------|
| `py_compile` (all 7 files) | PASS |
| `selfcheck_protocol.py` | PASS |
| `selfcheck_csv_roundtrip.py` | PASS |
| `selfcheck_geometry.py` | PASS |
| `selfcheck_fixtures.py` | PASS |
| `selfcheck_contract.py` (no forbidden tokens) | PASS |
| `selfcheck_mqtt_contract.py` (MQTT contract, alarm top-level 10 required keys) | PASS |
| `selfcheck_replay_alarm.py` (MCU + derived alarm edge checks) | PASS |
| `selfcheck_core.py` (core business calculations) | PASS |
| `selfcheck_input.py` (input adapter boundary) | PASS |
| `selfcheck_output.py` (output adapter boundary) | PASS |
| `selfcheck_all.ps1` full suite | PASS |

### 2.3 What Phase A Verified

- **ALLOWED_SPEEDS** whitelist: {0.5, 1.0, 2.0} only
- **disconnect** uses `wait_for_publish(timeout=...)`
- **status online** payload: `device_id`, `state`, `mode`, `version`, `ts`
- **status offline** payload: `device_id`, `state` only (no mode/version/ts)
- **telemetry** payload: all 10 required fields (including `reassembly` sub-object)
- **alarm** payload: top-level + `latest_point` sub-object fields, including `alarm_source`, `alarm_reason`, `threshold_cm`, and `min_distance_cm`
- **will** payload: `device_id` + `state=offline`
- **CmdDispatcher**: whitelist validation, REJECTED logging for illegal commands
- **Topic naming**: `lidar/{node_id}/{message_type}`
- **Replay alarm**: 0→3→0 triggers 2 publishes (alarm=true then alarm=false)
- **Alarm edge detection**: sustained alarm no duplicates, level changes detected, ESTIMATED flag (0x08) ignored, multi-point same frame captures all edges, derived distance/no-valid-points alarms covered

## 3. Phase B — Mosquitto + Paho Closed Loop

### 3.1 Environment

| Component | Status |
|-----------|--------|
| Mosquitto broker | localhost:1883, running |
| `mosquitto` | `C:\Program Files\mosquitto\mosquitto.exe` |
| `mosquitto_pub` | `C:\Program Files\mosquitto\mosquitto_pub.exe` |
| `mosquitto_sub` | `C:\Program Files\mosquitto\mosquitto_sub.exe` |
| Python | 3.12 with `paho-mqtt`, `python-can`, `PySide6`, `pyqtgraph` |
| Note | Mosquitto is installed but not on PATH; use absolute path or `tools/mqtt_closed_loop.ps1` |

### 3.2 Smoke Test (`mqtt_smoke_test.py`)

**Run command**:
```bash
python mqtt_smoke_test.py --duration 15
```

**Verified outputs**:
- `[OK] Connected to MQTT broker` — connection established
- `[PUB] status → lidar/01/status` — status online published
- `[PUB] telemetry → lidar/01/telemetry` — telemetry published
- `[CMD] ← payload={"cmd":"ping","req_id":"t01"}` — command received
- `[PUB] status offline → lidar/01/status` — explicit offline on exit
- `[OK] smoke test done` — clean exit with `wait_for_publish`

### 3.3 Replay + MQTT (`can_recv4.py`)

**Run command**:
```bash
python can_recv4.py --mode replay --input-csv docs\m4\data\can_distance_v2_sample.csv
```

**Subscriber (terminal A)**:
```bash
mosquitto_sub -h localhost -t "lidar/01/#" -v
```

**Command publisher (terminal C)**:
```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"ping\",\"req_id\":\"r01\"}" -q 1
mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"pause_replay\",\"req_id\":\"r02\"}" -q 1
mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"resume_replay\",\"req_id\":\"r03\"}" -q 1
mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"set_replay_speed\",\"speed\":2.0,\"req_id\":\"r04\"}" -q 1
mosquitto_pub -h localhost -t "lidar/01/cmd" -m "{\"cmd\":\"not_allowed\",\"req_id\":\"r05\"}" -q 1
```

### 3.4 Replay + MQTT Results

| Check | Result | Detail |
|-------|--------|--------|
| Status online (mode=replay) | PASS | `{"device_id":"lidar-01","state":"online","mode":"replay","version":"1.0.0","ts":...}` |
| Telemetry periodic publish | PASS | 2-second throttle, all 10 required fields |
| Cmd ping | PASS | `result=OK` |
| Cmd pause_replay | PASS | `result=OK (already paused)` |
| Cmd resume_replay | PASS | `result=OK` |
| Cmd set_replay_speed 2.0 | PASS | `result=OK speed=2` |
| Cmd not_allowed (illegal) | PASS | `result=REJECTED unknown_command` |
| Status offline on exit | PASS | `{"device_id":"lidar-01","state":"offline"}` |

**Log files**: `manual_replay_valid_json_stdout.txt`, `manual_replay_sub_log_valid_json.txt`

### 3.5 Automation Script

`tools/mqtt_closed_loop.ps1` — Automates smoke test verification. Status: PASS again on 2026-05-10 with broker on `localhost:1883`, two `ping` commands observed, telemetry published, and offline status published on clean exit.

## 3.6 Windows Board MQTT Verification (2026-05-09)

Windows 上板验证使用 `candleLight USB to CAN adapter`，`python-can` backend 为 `gs_usb`，本地 Broker 为 `localhost:1883`。最小闭环命令：

```powershell
python can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000 --mqtt
```

Verified:

- Real live CAN data entered the program: `seq` increased continuously with live fields such as `distance=36cm`, `angle=106.59deg` to `119.57deg`, `quality=255`, and `t_sample_us=...`.
- MQTT subscriber received live telemetry: `lidar/01/telemetry` with `"mode": "live"`, `point_count` around 800, `min_distance_cm` around 36-38, and increasing `reassembly.ok`.
- MQTT command path worked: `lidar/01/cmd {"cmd":"ping","req_id":"board_ping"}` and program log `MQTT cmd: cmd=ping req_id=board_ping result=OK`.
- Normal shutdown published offline: `lidar/01/status {"device_id":"lidar-01","state":"offline"}`.
- Broker-disconnect resilience was verified with a temporary Mosquitto broker on port `1884`: after stopping the broker, live CAN/UI continued running; after restarting the broker and subscriber, MQTT traffic resumed.
- Derived hardware alarm publication was verified by blocking / near-obstacle testing. The subscriber observed `lidar/01/alarm` events with `derived_too_near`, `derived_no_valid_points`, and `derived_near_obstacle`. Telemetry continued in parallel, which is expected because telemetry is a periodic status snapshot while alarm is a state-change event.
- `latest_status=8` in the telemetry/alarm context is `STATUS_ESTIMATED` (`0x08`), not an MCU-native alert bit. The accepted board-side MQTT closure is therefore gateway-derived alarm semantics.

Archived evidence:

- `docs/mqtt_plugin_refactor/evidence/2026-05-08_windows_selfcheck_and_mqtt_closed_loop.txt`
- `docs/mqtt_plugin_refactor/evidence/2026-05-08_windows_replay_program_log.txt`
- `docs/mqtt_plugin_refactor/evidence/2026-05-08_windows_replay_mqtt_sub_log.txt`
- `docs/mqtt_plugin_refactor/evidence/2026-05-09_windows_replay_cmd_log.txt`
- `docs/mqtt_plugin_refactor/evidence/2026-05-10_windows_board_derived_alarm_observed.md`
- Conversation screenshots for live CAN + MQTT terminal evidence.

## 4. Phase C — Documentation & Local Closure (Prompts 13 + 14)

### 4.1 Documentation Delivered

| Document | Description |
|----------|------------|
| `00_checkpoint3_overview.md` | Index and phase overview (updated) |
| `01_architecture_and_scope.md` | Architecture design and scope boundaries |
| `02_mqtt_and_broker_notes.md` | MQTT/Broker/Topic/QoS concepts mapped to project |
| `03_topic_interface_and_test.md` | Topic contract: payload fields, QoS, commands, test plan |
| `04_ai_prompt_workflow.md` | Step-by-step AI prompt execution manual (Prompts 1-15) |
| `05_prompt1_four_layer_plan.md` | Initial four-layer split plan from Prompt 1 |
| `06_m6_5_phase_b_closed_loop.md` | Phase B closed-loop verification procedure and results |
| `07_module_architecture.md` | Current module architecture (can_*.py), data flow, interface contracts — updated for Prompt 14 |
| `08_m6_5_verification_record.md` | This document: full verification record across all phases |
| `09_windows_replay.md` | Windows replay/live CAN entry points and current validation boundary |
| `10_m6_5_windows_board_mqtt.md` | Windows board-side MQTT verification record |
| `evidence/2026-05-10_windows_board_derived_alarm_observed.md` | Derived hardware alarm evidence from board-side MQTT subscription |

### 4.2 Prompt 14: Four Remaining Checkboxes Closed

Prompt 14 addressed four M6.5 Notion checkboxes that were partially complete:

**1. Unified input layer** — `can_input.py`:
- `InputAdapter` base class with `close()`, `source_name`, `mode` protocol
- `CsvReplaySource` now has `close()`, `source_name`, `mode` properties
- `SerialCanSource` reserved stub with full class definition; `read_frame()` raises `NotImplementedError` (not pretending complete)
- Three data source paths distinguishable: CAN live / CSV replay / serial-reserved
- Verified by: `tools/selfcheck_input.py`

**2. Core business calculations** — `can_core.py`:
- `compute_min_distance(points)` → `(cm, deg)` or `(None, None)`
- `compute_sector_summary(points)` → per-sector point_count/min_distance/alert_level
- `compute_alarm_state(point)` → `(alert_level, is_alert)`, ESTIMATED excluded
- `build_telemetry_dict(...)` → full telemetry payload (10 required fields)
- `compute_device_summary(...)` → comprehensive status dict with sectors
- All functions are pure — no PySide6/pyqtgraph/Paho/CSV dependencies
- Verified by: `tools/selfcheck_core.py`

**3. Output adapter layer** — `can_output.py` + `can_mqtt.py`:
- `OutputAdapter` base class with `close()`, `adapter_name`
- `LogOutputAdapter` — emits structured device summary to console (2s throttle)
- `CsvPointWriter` (csv adapter) — fully implemented
- `MqttOutput` (mqtt adapter in `can_mqtt.py`) — fully implemented
- `PointCloudWindow` (ui adapter in `can_recv4.py`) — boundary documented
- Verified by: `tools/selfcheck_output.py`
- Old MQTT output module names have been removed from implementation guidance

**4. UI enhancements** — `can_recv4.py`:
- 2D point cloud: preserved (existing)
- Status panel: mode, visible/sweep point count, min distance, alarm level, MQTT status, replay progress, reassembly stats
- Sector summary panel: **NEW** — 4 sectors (Front/Right/Rear/Left) with point_count, min_distance_cm, alert level
- Alarm area: Header alarm metric reflects latest point status (alertLv/normal with dynamic styling)
- Replay controls: play/pause, speed 0.5x/1x/2x, timeline slider — all preserved

### 4.3 UI Evidence

UI evidence requires screenshots from a running session. The following should be captured in replay mode:

- [x] 2D point cloud main view with visible sweep arcs (`ui_replay_prompt14.png`)
- [x] Status panel showing mode, point count, sweep count, min distance, MQTT status, alarm status
- [x] Sector summary panel (Front/Right/Rear/Left breakdown)
- [x] Replay controls (play/pause, speed selector, time slider)
- [x] Console output showing MQTT command log lines (`phase_b_smoke_test_log.txt`)
- [ ] mosquitto_sub terminal showing received telemetry (requires Mosquitto)

## 5. Notion Checklist

### Can Check Off (evidence available, no hardware required)

| Item | Evidence |
|------|----------|
| Unified input layer (CAN + CSV + serial reserved) | `can_input.py`: InputAdapter + CsvReplaySource + SerialCanSource stub; `selfcheck_input.py` PASS |
| Core business calculations | `can_core.py`: compute_min_distance, compute_sector_summary, compute_alarm_state, build_telemetry_dict, compute_device_summary; `selfcheck_core.py` PASS |
| Output adapter layer (csv, log, mqtt, ui) | `can_output.py`: OutputAdapter + CsvPointWriter + LogOutputAdapter; `can_mqtt.py`: MqttOutput; `can_recv4.py`: PointCloudWindow (ui, boundary documented) |
| UI: 2D point cloud + status panel + sector summary + alarm + replay | `can_recv4.py`: sector_panel_label, status_panel_label, alarm_metric, replay controls all present |
| Four-layer code split (can_*.py) | `07_module_architecture.md`, all py_compile pass |
| MQTT output plugin (can_mqtt.py) | `selfcheck_mqtt_contract.py` PASS, Phase B verification |
| MQTT contract document (03) | `03_topic_interface_and_test.md` |
| Alarm detection per-point (live + replay) | `selfcheck_replay_alarm.py` and `selfcheck_core.py` cover MCU status-bit alarms plus derived distance/no-valid-points alarms |
| Command whitelist (4 commands) | Phase B manual verification PASS |
| Code contract self-checks | `selfcheck_all.ps1` full suite PASS (includes core + input) |
| Mosquitto + Paho closed loop | `tools/mqtt_closed_loop.ps1` PASS on this machine |
| Windows board live CAN + MQTT minimum loop | `10_m6_5_windows_board_mqtt.md`: candleLight `gs_usb`, real live points, live telemetry, `cmd=ping`, offline status |
| Broker disconnect resilience in live mode | Temporary Mosquitto on `1884`; stopping broker did not stop live CAN/UI, restarting broker restored MQTT traffic |
| Windows board derived hardware alarm publication | `2026-05-10_windows_board_derived_alarm_observed.md`: `lidar/01/alarm` observed for `derived_too_near`, `derived_no_valid_points`, and `derived_near_obstacle` |

### NOT Ready to Check Off (require hardware or are out of scope)

| Item | Reason |
|------|--------|
| Serial input (real) | Implemented as reserve stub (`SerialCanSource`); real serial read NOT implemented |
| Full manual UI screenshot set with MQTT | Offscreen screenshot captured; screenshots showing sector panel recommended; MQTT-integrated screenshots need Mosquitto running |
| ESP32 integration | Out of M6.5 scope entirely |
| Cloud platform integration | Out of M6.5 scope entirely |

### Classification Summary

**可以打勾 (can check off — Prompt 14 closure):**
1. ✅ 统一输入层，兼容 CAN、串口与 CSV 回放三类数据源
2. ✅ 核心层固化业务计算：点云变换、扇区统计、最小距离、告警判定、设备状态汇总
3. ✅ 输出层提供可替换适配器：csv_output、log_output、mqtt_output、ui_output (boundary documented)
4. ✅ 重构 UI：保留实时 2D 点云，并补状态面板、扇区摘要、告警区与回放控制

**仍留到上板 (Phase D / Prompt 15):**
- 已完成：真实硬件派生告警触发，`lidar/01/alarm` 已发布 `derived_too_near` / `derived_no_valid_points` / `derived_near_obstacle`

**已完成上板最小闭环 (2026-05-09):**
- Windows candleLight `gs_usb` live 模式真实 CAN + MQTT
- live telemetry 发布
- `cmd=ping` 命令接收与程序日志确认
- 正常关闭发布 `status offline`
- broker 断开时真实 live 主链路不受影响，恢复 broker 后 MQTT 恢复
- 派生硬件告警发布：遮挡/近距离场景下 `lidar/01/alarm` 可观测

**不属于 M6.5:**
- ESP32
- 云平台
- 全量原始点云 MQTT 上传

## 6. Next Steps

### Selfcheck Verification Commands

Run these locally to confirm Prompt 14 closure:

```powershell
# Individual checks
python -m py_compile can_recv4.py can_parser.py can_input.py can_core.py can_output.py can_mqtt.py mqtt_smoke_test.py
python tools/selfcheck_core.py
python tools/selfcheck_input.py

# Full suite (includes new core + input checks)
powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1
```

### UI Screenshot

To capture UI evidence with sector summary visible:
```bash
set QT_QPA_PLATFORM=offscreen
python can_recv4.py --mode replay --input-csv docs\m4\data\can_distance_v2_sample.csv --no-mqtt
```

### Phase D (Hardware Verification — Prompt 15)
1. Connect real CAN hardware. Windows verified path: candleLight USB-CAN with `gs_usb`.
2. Start live mode: `python can_recv4_windows.py --mode live --can-interface gs_usb --channel 0 --bitrate 500000 --mqtt`.
3. Verify: UI shows real-time 2D point cloud, CSV writes, MQTT publishes. **Status: MQTT minimum loop PASS on 2026-05-09.**
4. Verify: normal shutdown publishes offline. **Status: PASS on 2026-05-09.**
5. Verify: MQTT broker unavailable does not break CAN/UI/CSV. **Status: PASS on 2026-05-09 with temporary broker on port 1884.**
6. Trigger derived hardware alarm with blocking / near-obstacle conditions. **Status: PASS on 2026-05-10; `lidar/01/alarm` observed with `derived_too_near`, `derived_no_valid_points`, and `derived_near_obstacle`.**
7. Archive: CAN log, CSV output, MQTT subscription log, UI screenshot. **Status: PASS for M6.5 MQTT scope; MQTT logs and screenshots archived/referenced.**

## 7. MQTT Stage Closure

M6.5 MQTT is closed for the current scope:

- Topic contract: `status`, `telemetry`, `alarm`, `cmd`, `config` documented.
- Local Mosquitto + Paho smoke loop: PASS.
- Replay + MQTT command/alarm path: PASS.
- Windows board live CAN + MQTT: PASS on candleLight `gs_usb`.
- Broker disconnect resilience: PASS with temporary broker on port `1884`.
- Derived hardware alarm publication: PASS with `derived_too_near`, `derived_no_valid_points`, and `derived_near_obstacle`.

Out of M6.5 scope: ESP32, cloud platform integration, TLS/auth, and full raw point-cloud upload over MQTT.

### Future Work (Post M6.5)
- Prompt 10: Further UI enhancement if needed
- Serial input real implementation (currently reserved stub)
- Geometry quality validation (M5/M6)
