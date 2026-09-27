#!/usr/bin/env python3
"""
mqtt_smoke_test.py — MQTT 最小闭环烟雾测试。

用例:
  1. 连接本机 Mosquitto broker
  2. 发布 status online (lidar/01/status, QoS 1, retain)
  3. 发布一条 telemetry (lidar/01/telemetry, QoS 0)
  4. 订阅 lidar/01/cmd (QoS 1)
  5. 收到命令后在回调中打印
  6. 退出时发布 status offline (wait_for_publish 超时 1s), 清理连接

Payload 与 docs/mqtt_plugin_refactor/03_topic_interface_and_test.md 契约一致。

前置条件:
  - Mosquitto broker 在本机运行 (默认 localhost:1883)
  - paho-mqtt 已安装 (pip install paho-mqtt)

用法:
  python mqtt_smoke_test.py [--host HOST] [--port PORT] [--client-id ID]

调试命令 (另开终端):
  # 监听所有 lidar topic
  mosquitto_sub -t 'lidar/01/#' -v

  # 发送 ping 命令
  mosquitto_pub -t 'lidar/01/cmd' -m '{"cmd":"ping"}' -q 1
"""

import argparse
import json
import signal
import sys
import time

try:
    from paho.mqtt import client as mqtt  # pyright: ignore[reportMissingImports]
except ImportError:
    print("请先安装 paho-mqtt: pip install paho-mqtt", file=sys.stderr)
    print("如在项目 venv 中: can-venv/bin/pip install paho-mqtt", file=sys.stderr)
    sys.exit(1)

# ── 常量 (与 03 契约一致) ─────────────────────────────────────────

NODE_ID = "01"
DEVICE_ID = "lidar-01"
VERSION = "1.0.0"

TOPIC_STATUS = f"lidar/{NODE_ID}/status"
TOPIC_TELEMETRY = f"lidar/{NODE_ID}/telemetry"
TOPIC_ALARM = f"lidar/{NODE_ID}/alarm"
TOPIC_CMD = f"lidar/{NODE_ID}/cmd"


# ── 回调 ──────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[OK] 已连接 MQTT broker (rc={rc})")
        client.subscribe(TOPIC_CMD, qos=1)
        print(f"[SUB] 已订阅 {TOPIC_CMD}")
    else:
        print(f"[FAIL] 连接失败 (rc={rc})", file=sys.stderr)
        print("  rc=1: 协议版本不匹配", file=sys.stderr)
        print("  rc=2: client_id 被拒绝", file=sys.stderr)
        print("  rc=3: broker 不可用", file=sys.stderr)
        print("  rc=4: 用户名/密码错误", file=sys.stderr)
        print("  rc=5: 未授权", file=sys.stderr)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        print(
            f"[CMD] ← topic={msg.topic} "
            f"qos={msg.qos} "
            f"payload={json.dumps(payload, ensure_ascii=False)}"
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[CMD] ← topic={msg.topic} raw={msg.payload!r} (解析失败: {exc})")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[WARN] 异常断开 (rc={rc})")
    else:
        print("[OK] 正常断开连接")


def on_publish(client, userdata, mid):
    print(f"[PUB] 消息已确认 mid={mid}")


# ── 主流程 ────────────────────────────────────────────────────────

def make_status_online():
    """构建 status online payload (03 §5.3.1)."""
    return {
        "device_id": DEVICE_ID,
        "state": "online",
        "mode": "live",
        "version": VERSION,
        "ts": int(time.time() * 1000),
    }


def make_status_offline():
    """构建 status offline payload (03 §5.3.1)."""
    return {
        "device_id": DEVICE_ID,
        "state": "offline",
    }


def make_telemetry():
    """构建 telemetry payload (03 §5.3.2)."""
    now_ms = int(time.time() * 1000)
    return {
        "device_id": DEVICE_ID,
        "mode": "live",
        "ts": now_ms,
        "point_count": 42,
        "sweep_point_count": 18,
        "min_distance_cm": 15,
        "min_distance_angle_deg": 90.5,
        "latest_quality": 12,
        "latest_status": 0,
        "reassembly": {
            "ok": 100,
            "timeout": 0,
            "overwrite_a": 0,
            "overwrite_b": 0,
            "pending": 0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="MQTT 最小闭环烟雾测试")
    parser.add_argument("--host", default="localhost", help="MQTT broker 地址")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker 端口")
    parser.add_argument("--client-id", default="ladar2_smoke_test", help="MQTT client ID")
    parser.add_argument("--duration", type=float, default=0,
                        help="auto-exit after N seconds (0 = wait for Ctrl+C)")
    args = parser.parse_args()

    auto_exit = args.duration > 0
    deadline = time.monotonic() + args.duration if auto_exit else None

    print(f"MQTT 烟雾测试 — broker={args.host}:{args.port} client_id={args.client_id}")
    print()

    # ── 创建 client ──────────────────────────────────────────

    client = mqtt.Client(client_id=args.client_id, protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    # Will: 异常断开时 Broker 代替发布 offline (03 §5.3.1)
    will_payload = json.dumps(make_status_offline(), ensure_ascii=False)
    client.will_set(TOPIC_STATUS, will_payload, qos=1, retain=True)

    # ── 连接 ─────────────────────────────────────────────────

    try:
        client.connect(args.host, args.port, keepalive=10)
    except ConnectionRefusedError:
        print(f"[FAIL] 无法连接 {args.host}:{args.port}", file=sys.stderr)
        print("  请确认 Mosquitto 已启动:", file=sys.stderr)
        print("    sudo systemctl start mosquitto", file=sys.stderr)
        print("  或手动启动:", file=sys.stderr)
        print("    mosquitto -p 1883", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"[FAIL] 网络错误: {exc}", file=sys.stderr)
        sys.exit(1)

    client.loop_start()

    # ── 发布 status online (03 §5.3.1) ───────────────────────

    status_payload = json.dumps(make_status_online(), ensure_ascii=False)
    client.publish(TOPIC_STATUS, status_payload, qos=1, retain=True)
    print(f"[PUB] status → {TOPIC_STATUS}: {status_payload}")

    # 等待连接和订阅完成
    time.sleep(0.3)

    # ── 发布 telemetry (03 §5.3.2) ───────────────────────────

    telemetry = make_telemetry()
    telemetry_payload = json.dumps(telemetry, ensure_ascii=False)
    client.publish(TOPIC_TELEMETRY, telemetry_payload, qos=0)
    print(f"[PUB] telemetry → {TOPIC_TELEMETRY}: {telemetry_payload}")

    # ── 等待命令 ─────────────────────────────────────────────

    print()
    print("=" * 64)
    print("  最小闭环已就绪。请在另一个终端发送命令验证:")
    print(f"    mosquitto_pub -t '{TOPIC_CMD}' -m '{{\"cmd\":\"ping\"}}' -q 1")
    print("=" * 64)
    print()
    if auto_exit:
        print(f"等待命令中... ({args.duration:.0f}s 后自动退出)")
    else:
        print("等待命令中... (Ctrl+C 退出)")
    sys.stdout.flush()

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while running:
            if auto_exit and time.monotonic() >= deadline:
                print("(duration reached, exiting)")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    # ── 清理 (03 §8.4) ───────────────────────────────────────

    print("\n正在退出...")

    # 正常关闭时主动发布 offline (03 §8.4)
    offline_payload = json.dumps(make_status_offline(), ensure_ascii=False)
    info = client.publish(TOPIC_STATUS, offline_payload, qos=1, retain=True)
    print(f"[PUB] status offline → {TOPIC_STATUS}: {offline_payload}")

    # wait_for_publish 超时 1s 确保离线消息已送达 (03 §8.4)
    info.wait_for_publish(timeout=1.0)

    client.loop_stop()
    client.disconnect()
    print("[OK] 烟雾测试结束")


if __name__ == "__main__":
    main()
