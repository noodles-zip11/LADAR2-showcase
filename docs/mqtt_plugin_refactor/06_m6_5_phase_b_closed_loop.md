# M6.5 Phase B — MQTT 最小闭环验证记录

> **日期**: 2026-05-05
> **前提**: Phase A (Prompt 11) 已完成，代码合同已闭合
> **约束**: 不上板、不接真实 CAN 硬件，仅验证本机 Mosquitto + Paho 闭环

## 1. 验证目标

| # | 验收项 | 验收方式 |
|---|--------|---------|
| 1 | status online payload 字段符合 03 合同 | mosquitto_sub 订阅验证 |
| 2 | status offline payload 字段符合 03 合同 | mosquitto_sub 订阅验证 |
| 3 | telemetry payload 字段符合 03 合同 | mosquitto_sub 订阅验证 |
| 4 | cmd 回调可观测 | mqtt_smoke_test.py stdout |
| 5 | set_replay_speed 只接受 0.5 / 1.0 / 2.0 | selfcheck_mqtt_contract.py |
| 6 | 正常退出能发布 offline (wait_for_publish) | mosquitto_sub + smoke log |
| 7 | can_recv4.py replay 模式发布 status/telemetry/alarm | mosquitto_sub 订阅验证 |

## 2. 环境要求

### 2.1 Mosquitto Broker

**Windows 安装**: 下载 Mosquitto Windows 安装包 https://mosquitto.org/download/

**WSL/Linux 安装**:
```bash
sudo apt install mosquitto mosquitto-clients
```

**启动**:
```bash
# Windows (CMD 或 PowerShell)
mosquitto -p 1883

# Linux
sudo systemctl start mosquitto
# 或手动: mosquitto -p 1883
```

### 2.2 Python 依赖

```bash
pip install paho-mqtt
```

验证:
```bash
python -c "import paho.mqtt.client; print('OK')"
```

## 3. 测试 A — mqtt_smoke_test.py 最小闭环

### 3.1 运行方式

**自动化脚本** (推荐):
```powershell
powershell -ExecutionPolicy Bypass -File .\tools\mqtt_closed_loop.ps1
```

**手动步骤**:

终端 A — 订阅所有 lidar topic:
```bash
mosquitto_sub -h localhost -t "lidar/01/#" -v
```

终端 B — 运行 smoke test:
```bash
cd LADAR2
python mqtt_smoke_test.py
```

终端 C — 发送命令:
```bash
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"ping","req_id":"t01"}' -q 1
```

### 3.2 预期现象

**终端 B (smoke test) 输出**:
```
MQTT 烟雾测试 — broker=localhost:1883 client_id=ladar2_smoke_test

[OK] 已连接 MQTT broker (rc=0)
[SUB] 已订阅 lidar/01/cmd
[PUB] status → lidar/01/status: {"device_id":"lidar-01","state":"online","mode":"live","version":"1.0.0","ts":...}
[PUB] telemetry → lidar/01/telemetry: {"device_id":"lidar-01","mode":"live","ts":...,...}

================================================================
  最小闭环已就绪。请在另一个终端发送命令验证:
    mosquitto_pub -t 'lidar/01/cmd' -m '{"cmd":"ping"}' -q 1
================================================================

[CMD] ← topic=lidar/01/cmd qos=1 payload={"cmd":"ping","req_id":"t01"}

正在退出...
[PUB] status offline → lidar/01/status: {"device_id":"lidar-01","state":"offline"}
[OK] 烟雾测试结束
```

**终端 A (mosquitto_sub) 输出**:
```
lidar/01/status {"device_id":"lidar-01","state":"online","mode":"live","version":"1.0.0","ts":...}
lidar/01/telemetry {"device_id":"lidar-01","mode":"live","ts":...,"point_count":42,...}
lidar/01/status {"device_id":"lidar-01","state":"offline"}
```

### 3.3 Payload 字段对照 (03 合同)

**status online** (03 §5.3.1):
- `device_id` (string) — "lidar-01"
- `state` (string) — "online"
- `mode` (string) — "live" 或 "replay"
- `version` (string) — "1.0.0"
- `ts` (int) — Unix ms

**status offline** (03 §5.3.1):
- `device_id` (string) — "lidar-01"
- `state` (string) — "offline"
- **不包含** mode / version / ts

**telemetry** (03 §5.3.2):
- `device_id`, `mode`, `ts`, `point_count`, `sweep_point_count`
- `min_distance_cm`, `min_distance_angle_deg`
- `latest_quality`, `latest_status`
- `reassembly` (子对象: ok, timeout, overwrite_a, overwrite_b, pending)

## 4. 测试 B — can_recv4.py replay + MQTT 闭环

### 4.1 运行方式

终端 A — 订阅:
```bash
mosquitto_sub -h localhost -t "lidar/01/#" -v
```

终端 B — 启动 replay (使用现有 CSV fixture):
```bash
cd LADAR2
python can_recv4.py --mode replay --input-csv docs\m4\data\can_distance_v2_sample.csv
```

终端 C — 发送命令:
```bash
# ping
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"ping","req_id":"r01"}' -q 1

# pause
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"pause_replay","req_id":"r02"}' -q 1

# resume
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"resume_replay","req_id":"r03"}' -q 1

# set speed to 2x
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"set_replay_speed","speed":2.0,"req_id":"r04"}' -q 1

# 非法速度 (应被拒绝)
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"set_replay_speed","speed":5.0,"req_id":"r05"}' -q 1

# 非法命令 (应被拒绝)
mosquitto_pub -h localhost -t "lidar/01/cmd" -m '{"cmd":"reboot","req_id":"r06"}' -q 1
```

### 4.2 预期现象

**终端 B (can_recv4.py) 控制台输出**:
```
[MQTT] 异步连接 localhost:1883 ...
[MQTT] 命令白名单已注册: ping, pause_replay, resume_replay, set_replay_speed
加载回放 CSV: ...\can_distance_v2_sample.csv
[MQTT] 已连接 broker localhost:1883

MQTT cmd: cmd=ping req_id=r01 result=OK
MQTT cmd: cmd=pause_replay req_id=r02 result=OK
MQTT cmd: cmd=resume_replay req_id=r03 result=OK
MQTT cmd: cmd=set_replay_speed req_id=r04 result=OK speed=2
MQTT cmd: cmd=set_replay_speed req_id=r05 result=REJECTED invalid_speed(5.0)
MQTT cmd: cmd=reboot req_id=r06 result=REJECTED unknown_command
```

**终端 A (mosquitto_sub) 预期输出**:
```
lidar/01/status {"device_id":"lidar-01","state":"online","mode":"replay","version":"1.0.0","ts":...}
lidar/01/telemetry {"device_id":"lidar-01","mode":"replay","ts":...,"point_count":...,...}
lidar/01/telemetry ...  (每 2 秒一条)
...
lidar/01/status {"device_id":"lidar-01","state":"offline"}  (退出时)
```

**告警**: 如果 replay CSV 中包含 status & 0x07 != 0 的点，会在 alarm topic 看到状态变化:
```
lidar/01/alarm {"device_id":"lidar-01","ts":...,"alarm":true,"alarm_status":3,...}
lidar/01/alarm {"device_id":"lidar-01","ts":...,"alarm":false,"alarm_status":0,...}
```

## 5. 命令合规验证

| 命令 | payload 格式 | 约束 |
|------|-------------|------|
| ping | `{"cmd":"ping","req_id":"..."}` | 任意模式可用 |
| pause_replay | `{"cmd":"pause_replay","req_id":"..."}` | 仅 replay 模式，幂等 |
| resume_replay | `{"cmd":"resume_replay","req_id":"..."}` | 仅 replay 模式，幂等 |
| set_replay_speed | `{"cmd":"set_replay_speed","speed":N,"req_id":"..."}` | 仅 replay 模式，speed ∈ {0.5, 1.0, 2.0} |
| 任何非法命令 | — | 日志: REJECTED unknown_command |

## 6. 验证结果汇总

实际运行结果（2026-05-05，本机 Mosquitto + Paho）:

| # | 验收项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | Mosquitto broker 可用 | ✅ | `C:\Program Files\mosquitto\mosquitto.exe`, localhost:1883 |
| 2 | mqtt_smoke_test.py status online | ✅ | `phase_b_smoke_test_log.txt` |
| 3 | mqtt_smoke_test.py telemetry | ✅ | `phase_b_smoke_test_log.txt` |
| 4 | mqtt_smoke_test.py cmd 回调 | ✅ | `t01` / `t02` 均收到 |
| 5 | mqtt_smoke_test.py offline | ✅ | 退出时发布，`wait_for_publish` 完成 |
| 6 | can_recv4.py replay status online | ✅ | `manual_replay_sub_log_valid_json.txt`, mode="replay" |
| 7 | can_recv4.py replay telemetry | ✅ | `manual_replay_sub_log_valid_json.txt`, 2s 节流 |
| 8 | can_recv4.py cmd ping | ✅ | `manual_replay_valid_json_stdout.txt`, result=OK |
| 9 | can_recv4.py cmd pause_replay | ✅ | `manual_replay_valid_json_stdout.txt`, result=OK |
| 10 | can_recv4.py cmd resume_replay | ✅ | `manual_replay_valid_json_stdout.txt`, result=OK |
| 11 | can_recv4.py cmd set_replay_speed | ✅ | speed=2.0 OK；白名单由 selfcheck 覆盖 |
| 12 | can_recv4.py 非法命令拒绝 | ✅ | `not_allowed` -> REJECTED unknown_command |
| 13 | can_recv4.py 正常退出 offline | ✅ | `can_mqtt.py` + `selfcheck_mqtt_contract.py` 覆盖；smoke test 实测 offline |
| 14 | set_replay_speed 白名单 | ✅ | `selfcheck_mqtt_contract.py` 已验证 |
| 15 | 不上板可验证项完成 | ✅ | Phase B 完成 |

## 7. 仍需上板验证的项

以下项在 Phase B 无法验证，留到 Phase D:

- live 模式真实 CAN 接收 + MQTT 发布
- 真实硬件告警触发 (status & 0x07 != 0)
- MQTT 断开时不影响 CAN/UI/CSV 主链路
- 长时间运行稳定性
- CSV summary 输出
