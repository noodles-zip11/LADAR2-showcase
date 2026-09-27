# Module Architecture — Current Implementation

> **Date**: 2026-05-05
> **Status**: Reflects code as of Prompt 14 completion (Phase C final)

## 1. Why `can_*.py` Flat Structure

During Prompt 1-6 (four-layer split), the original plan called for a `lidar/` package with nested modules. After implementation, the final structure uses flat `can_*.py` files at the project root. This decision was made for two reasons:

- **Minimal import friction**: All modules live at the same level as the main entry point (`can_recv4.py`), so `from can_parser import ...` works regardless of working directory. This matters for tools in `tools/` that import from the project root with `sys.path` manipulation.
- **No circular dependency risk**: A flat module structure with clear naming conventions (`can_input`, `can_parser`, `can_core`, `can_output`, `can_mqtt`) makes the dependency direction obvious and prevents accidental cross-layer imports.

## 2. Module Map

```
LADAR2/
  can_recv4.py      — Main entry point + PySide6 UI + scheduling
  can_input.py       — Input layer (CAN live, CSV replay)
  can_parser.py      — Parser layer (CAN dual-frame assembly, LidarPoint, CSV constants)
  can_core.py        — Core layer (geometry, sweep extraction, pure computation)
  can_output.py      — Output layer (CSV writing, formatting)
  can_mqtt.py        — MQTT output plugin (publish/subscribe, command dispatcher)
  mqtt_smoke_test.py — Standalone MQTT closed-loop smoke test
```

## 3. Layer Responsibilities

### 3.1 Input Layer — `can_input.py`

**What it does**: Abstracts data sources so the rest of the system doesn't care where points come from.

| Component | Role |
|-----------|------|
| `InputAdapter` | Base class / protocol: `close()`, `source_name`, `mode` |
| `open_bus(channel)` | Opens a socketcan bus for live mode |
| `CsvReplaySource` | Loads a CSV file and provides time-indexed point access; conforms to `InputAdapter` (close, source_name, mode) |
| `CsvReplaySource.visible_points(us, window)` | Returns points within the replay time window |
| `CsvReplaySource.latest_point(us)` | Returns the most recent point at a given replay time |
| `CsvReplaySource.stats_snapshot()` | Returns reassembly stats dict (`ok`, `timeout`, `overwrite_a`, `overwrite_b`, `pending`) |
| `SerialCanSource` | **Reserved stub** — class name, constructor signature, `read_frame()` defined; raises `NotImplementedError`; does NOT pretend serial is complete |

**Exports**: `LidarPoint` sequences (via parser underneath), time-indexed access, replay statistics.

**Data source selection in `can_recv4.py`**: Three paths are clearly distinguishable:
- **CAN live**: `open_bus(channel)` → `CanPointAssembler` → `poll_live_bus()`
- **CSV replay**: `CsvReplaySource(csv_path)` → `advance_replay()`
- **Serial reserved**: `SerialCanSource(port, baudrate)` → NOT YET IMPLEMENTED

### 3.2 Parser Layer — `can_parser.py`

**What it does**: Converts raw CAN messages into structured `LidarPoint` objects.

| Component | Role |
|-----------|------|
| `CanPointAssembler` | Handles dual-frame CAN message reassembly (0x123 + 0x124) |
| `CanPointAssembler.process_message(msg)` | Accepts a `can.Message`, yields complete `LidarPoint` objects |
| `CanPointAssembler.prune_stale_frames()` | Removes incomplete frames older than a timeout |
| `CanPointAssembler.stats_snapshot()` | Returns reassembly counters |
| `LidarPoint` | Named tuple: `frame_id, host_rx_time_us, t_sample_us, angle_tick, angle_deg, distance_cm, quality, status, x_mm, y_mm` |
| `compute_xy_mm(distance_cm, angle_deg)` | Converts polar to Cartesian coordinates |
| `CSV_FIELDNAMES`, `CSV_PREFIX` | Standardized CSV column names and timestamp prefix |
| `STATUS_ALERT_MASK` | `= 0x07` — bitmask for alarm detection (bits [2:0]) |

**Exports**: `LidarPoint` objects (one per completed CAN dual-frame), CSV format constants, alarm mask.

**Key design rule**: `distance_mm` is an internal derived quantity only. The formal protocol field is `distance_cm`. No code should rename `distance_cm` to `distance_mm`.

### 3.3 Core Layer — `can_core.py`

**What it does**: Pure computation — geometry, statistics, sweep extraction, alarm, telemetry building. No I/O, no UI, no MQTT, no CSV handles.

| Component | Role |
|-----------|------|
| `angular_delta_deg(a, b)` | Angle delta with 360° wrap handling |
| `extract_recent_sweep(points)` | Extract most recent ~340° scan arc from point sequence |
| `build_sweep_curve(points)` | Build (xs, ys) curve with NaN breaks for rendering |
| `compute_min_distance(points)` | Returns `(min_distance_cm, min_angle_deg)` or `(None, None)` |
| `compute_sector_summary(points)` | Per-sector stats: `point_count`, `min_distance_cm`, `alert_level` for 4 quadrants (Front/Right/Rear/Left) |
| `compute_alarm_state(point)` | Extract `(alert_level, is_alert)` from point status, ESTIMATED flag (0x08) excluded |
| `compute_derived_alarm_state(...)` | Derive gateway-side alarm state from MCU status bits, recent-window distance, and no-valid-points timeout |
| `alarm_state_changed(previous, current)` | Publish alarm events only when alarm source/status/reason changes |
| `build_telemetry_dict(...)` | Build full telemetry payload dict (all 10 required fields per 03 contract) |
| `compute_device_summary(...)` | Comprehensive device summary dict: mode, counts, min dist, alarm, sectors, reassembly |
| `STATUS_ALERT_MASK` | `= 0x07` — bit [3] (ESTIMATED flag) is excluded from alarm detection |
| `STATUS_ESTIMATED` | `= 0x08` — estimated/interpolated point flag |
| `DEFAULT_SECTOR_DEFS` | `{"Front": (-45,45), "Right": (45,135), "Rear": (135,225), "Left": (225,315)}` |

**Exports**: Pure functions that accept point collections and return computed results. No side effects, no PySide6/pyqtgraph/Paho/csv dependencies.

### 3.4 Output Layer — `can_output.py`

**What it does**: Persists point data to CSV files and provides structured log output. Follows the adapter pattern.

| Component | Role |
|-----------|------|
| `OutputAdapter` | Base class / protocol: `close()`, `adapter_name` |
| `CsvPointWriter` | Writes points to timestamped CSV files; conforms to `OutputAdapter` |
| `CsvPointWriter.write_point(point)` | Appends one row |
| `CsvPointWriter.close()` | Finalizes CSV and writes summary |
| `LogOutputAdapter` | Console log output adapter; emits `compute_device_summary` dict as structured text |
| `LogOutputAdapter.emit_summary(summary)` | Prints mode, counts, min dist, alarm, sector breakdown |
| `build_default_csv_path()` | (in `can_recv4.py`) Generates timestamped output path |
| CSV summary generation | Computes and writes `_summary.txt` with frame statistics |

**Adapter inventory** (all follow OutputAdapter interface):
| Adapter | Location | Status |
|---------|----------|--------|
| `CsvPointWriter` (csv) | `can_output.py` | Fully implemented |
| `LogOutputAdapter` (log) | `can_output.py` | Fully implemented |
| `MqttOutput` (mqtt) | `can_mqtt.py` | Fully implemented |
| `PointCloudWindow` (ui) | `can_recv4.py` | Boundary documented; UI body kept in main entry for PySide6 coupling |

**Exports**: CSV writer objects, log adapter, path builders, formatting utilities.

### 3.5 MQTT Output Plugin — `can_mqtt.py`

**What it does**: Publishes device status, telemetry summaries, and alarm events to an MQTT broker. Subscribes to command topics for remote control.

| Component | Role |
|-----------|------|
| `MqttOutput` | Main MQTT client wrapper. Uses `connect_async()` + `loop_start()` for non-blocking operation |
| `MqttOutput.publish_status(state, mode)` | Publishes `lidar/{node_id}/status` (QoS 1, retain) |
| `MqttOutput.publish_telemetry(data)` | Publishes `lidar/{node_id}/telemetry` (QoS 0) |
| `MqttOutput.publish_alarm(data)` | Publishes `lidar/{node_id}/alarm` (QoS 1) |
| `MqttOutput.subscribe_cmd(callback)` | Sets the command callback for `lidar/{node_id}/cmd` |
| `MqttOutput.disconnect()` | Publishes offline status, calls `wait_for_publish(timeout=1.0)`, then disconnects |
| `CmdDispatcher` | Validates commands against `ALLOWED_COMMANDS` whitelist, dispatches to registered handlers |
| `ALLOWED_COMMANDS` | `{"ping", "pause_replay", "resume_replay", "set_replay_speed"}` |
| `ALLOWED_SPEEDS` | `{0.5, 1.0, 2.0}` |

**Topic naming** (03 contract, section 5.2.1): `lidar/{node_id}/{message_type}`

**Default configuration** (03 section 6.6):
- `host` = `"localhost"`, `port` = `1883`
- `node_id` = `"01"`, `device_id` = `"lidar-01"`
- `keepalive` = `30`, `telemetry_interval_s` = `2.0`

### 3.6 Main Entry — `can_recv4.py`

**What it does**: Wires all layers together. Owns the PySide6 UI, timers, and the top-level scheduling loop.

| Responsibility | Detail |
|---------------|--------|
| UI | PySide6-based 2D point cloud view, status panel, sector summary, alarm indicator, playback controls |
| UI: Sector summary | `sector_panel_label` shows per-sector point_count / min_distance / alert_level from `compute_sector_summary()` |
| UI: Status panel | Mode, visible/sweep point counts, min distance, alarm level, MQTT status, replay progress, reassembly stats |
| Live mode | `poll_live_bus()` timer → `CanPointAssembler` → `ingest_live_point()` → CSV + MQTT alarm |
| Replay mode | `advance_replay()` timer → time-indexed point access → `_check_and_publish_alarm()` → MQTT telemetry |
| Alarm detection | `_check_and_publish_alarm(point)` uses `compute_derived_alarm_state()` / `alarm_state_changed()` from `can_core`; called per-point in both live and replay paths |
| Replay alarm iteration | Uses `bisect_right` on `timeline_us` to iterate ALL new points since last check |
| Log output | `LogOutputAdapter` emits device summary every 2 seconds |
| MQTT telemetry | 2-second throttled publish from `refresh_status_labels()`, built via `build_telemetry_dict()` |
| Command handlers | Registered with `CmdDispatcher` for ping/pause_replay/resume_replay/set_replay_speed |
| Shutdown | `shutdown()` → log close → CSV close → MQTT disconnect (offline + wait_for_publish) |

## 4. Data Flow

```
Live Mode:
  socketcan bus → CanPointAssembler(process_message) → LidarPoint
    → ingest_live_point()
      → live_points list (UI)
      → CsvPointWriter (persistence)
      → _check_and_publish_alarm() → MqttOutput.publish_alarm()
    → refresh_status_labels()
      → UI status panel update
      → MqttOutput.publish_telemetry() [2s throttle]

Replay Mode:
  CsvReplaySource(points, timeline_us)
    → advance_replay()
      → bisect_right(timeline, _replay_last_alarm_time_us) → iterate new points
        → _check_and_publish_alarm() → MqttOutput.publish_alarm()
    → visible_points(replay_current_us, window) → UI
    → refresh_status_labels()
      → UI status panel update
      → MqttOutput.publish_telemetry() [2s throttle]

Command Flow:
  MQTT broker → CmdDispatcher.dispatch(topic, payload)
    → validate against ALLOWED_COMMANDS
    → call registered handler (ping/pause_replay/resume_replay/set_replay_speed)
    → log result with format: "MQTT cmd: cmd=xxx req_id=yyy result=zzz"
```

## 5. Interface Contracts

### 5.1 Input → Parser
`CanPointAssembler.process_message(can.Message) → Iterator[LidarPoint]`

### 5.2 Parser → Core
`LidarPoint` objects (named tuple with x_mm, y_mm, distance_cm, angle_deg, quality, status, etc.)

### 5.3 Core → Output/MQTT
Computed values: point counts, min distance/angle, sweep stats, alert levels.

### 5.4 Output/MQTT → External
- Topic payloads as defined in 03 contract (sections 5.3.1-5.3.3)
- Command log format: `"MQTT cmd: cmd=xxx req_id=yyy result=zzz"` (03 section 7.2 rule 5)

## 6. Serial Input Status

Serial input is acknowledged as a future input source but is **NOT** implemented and **NOT** included in M6.5 verification scope. The `can_input.py` module structure allows a future `SerialReplaySource` or `SerialLiveSource` to be added without changing the parser, core, or output layers.

## 7. What This Architecture Enables

- **Independent testing**: Each layer can be tested with mock inputs (see `tools/selfcheck_*.py`: protocol, csv_roundtrip, geometry, fixtures, contract, mqtt_contract, replay_alarm, core, input)
- **Offline verification**: The replay path exercises all MQTT logic without hardware
- **Graceful degradation**: If MQTT broker is unavailable, CAN/UI/CSV continue unaffected
- **Command safety**: Only whitelisted commands are dispatched; illegal commands log REJECTED
- **No cross-layer coupling**: Parser doesn't know about MQTT; core doesn't know about UI; MQTT doesn't touch CAN protocol
