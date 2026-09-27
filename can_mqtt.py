"""MQTT 输出层。

作为 output 层插件，通过 Paho MQTT 异步发布 status / telemetry / alarm，
并订阅 cmd topic 接收远程命令。

Topic 契约 (与 docs/mqtt_plugin_refactor/03_topic_interface_and_test.md 一致):
  lidar/{node_id}/status    — QoS 1, retain   (设备在线/离线)
  lidar/{node_id}/telemetry — QoS 0           (周期性遥测)
  lidar/{node_id}/alarm     — QoS 1           (告警状态变更)
  lidar/{node_id}/cmd       — QoS 1           (远程命令)

配置项 (03 §6.6):
  host                    Broker 地址 (默认 "localhost")
  port                    Broker 端口 (默认 1883)
  node_id                 节点编号，topic 路由用 (默认 "01")
  device_id               payload 内 device_id 字段值 (默认 "lidar-01")
  keepalive               心跳间隔秒数 (默认 30)
  telemetry_interval_s    telemetry 发布间隔秒数 (默认 2.0)
  enabled                 是否启用 (默认 True)
"""

import json
import sys
import time

try:
    from paho.mqtt import client as mqtt  # pyright: ignore[reportMissingImports]
except ImportError:
    mqtt = None

# ── 默认配置值 (03 §6.6) ──────────────────────────────────────────

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
DEFAULT_NODE_ID = "01"
DEFAULT_DEVICE_ID = "lidar-01"
DEFAULT_KEEPALIVE = 30
DEFAULT_TELEMETRY_INTERVAL_S = 2.0
VERSION = "1.0.0"


# ── 命令白名单 (03 §7.1) ──────────────────────────────────────────

ALLOWED_COMMANDS = {
    "ping",
    "pause_replay",
    "resume_replay",
    "set_replay_speed",
}

ALLOWED_SPEEDS = {0.5, 1.0, 2.0}


# ── 命令分发器 ─────────────────────────────────────────────────────

class CmdDispatcher:
    """命令分发器。

    验证命令是否在白名单内，然后将合法命令分发给注册的处理器。
    所有命令均按契约格式记录日志 (03 §7.2-rule-5)。

    使用方式:
        dispatcher = CmdDispatcher()
        dispatcher.register("ping", lambda t, p: ...)
        在 on_message/mqtt 回调中调用 dispatcher.dispatch(topic, payload)
    """

    def __init__(self):
        self._handlers = {}

    def register(self, cmd_name: str, handler):
        """注册命令处理器。

        handler 签名: handler(topic: str, payload: dict)
        """
        if cmd_name not in ALLOWED_COMMANDS:
            raise ValueError(f"命令 {cmd_name!r} 不在白名单内")
        self._handlers[cmd_name] = handler

    def dispatch(self, topic, payload):
        """分发命令。

        日志格式: MQTT cmd: cmd=xxx req_id=yyy result=zzz (03 §7.2-rule-5)
        result 取值: OK / REJECTED_unknown_command / REJECTED_no_handler
        """
        cmd = (payload.get("cmd") or "").strip()
        req_id = payload.get("req_id", "")

        if not cmd:
            print(f"MQTT cmd: cmd= req_id={req_id} result=REJECTED missing_cmd_field", flush=True)
            return

        if cmd not in ALLOWED_COMMANDS:
            print(f"MQTT cmd: cmd={cmd} req_id={req_id} result=REJECTED unknown_command", flush=True)
            return

        handler = self._handlers.get(cmd)
        if handler is None:
            print(f"MQTT cmd: cmd={cmd} req_id={req_id} result=REJECTED no_handler", flush=True)
            return

        try:
            handler(topic, payload)
        except Exception as exc:
            print(f"MQTT cmd: cmd={cmd} req_id={req_id} result=EXCEPTION {exc}",
                  file=sys.stderr, flush=True)


# ── MqttOutput 类 ─────────────────────────────────────────────────

class MqttOutput:
    """MQTT 输出插件。

    使用 paho-mqtt 的 loop_start() / connect_async() 在后台线程处理网络 I/O，
    不阻塞主程序 CAN 接收和 replay 循环。连接失败时降级运行，不阻塞 UI 启动 (03 §8.1)。

    Topic 命名规则: lidar/{node_id}/{message_type} (03 §5.2.1)
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 node_id=DEFAULT_NODE_ID, device_id=DEFAULT_DEVICE_ID,
                 keepalive=DEFAULT_KEEPALIVE,
                 telemetry_interval_s=DEFAULT_TELEMETRY_INTERVAL_S,
                 enabled=True):
        if mqtt is None:
            raise ImportError("paho-mqtt 未安装。请执行: pip install paho-mqtt")

        self.host = host
        self.port = port
        self.node_id = node_id
        self.device_id = device_id
        self.keepalive = keepalive
        self.telemetry_interval_s = telemetry_interval_s
        self.enabled = enabled
        self.client = None
        self.connected = False
        self._mode = "live"  # 当前运行模式，由 set_mode() 更新
        self._cmd_callback = self._default_on_cmd

        # 构建 topic 路径 (03 §5.2.1)
        prefix = f"lidar/{node_id}"
        self.topic_status = f"{prefix}/status"
        self.topic_telemetry = f"{prefix}/telemetry"
        self.topic_alarm = f"{prefix}/alarm"
        self.topic_cmd = f"{prefix}/cmd"

    @property
    def adapter_name(self):
        return "mqtt"

    # ── 内部: 默认命令回调 ─────────────────────────────────────

    def _default_on_cmd(self, topic, payload):
        cmd = (payload.get("cmd") or "").strip()
        req_id = payload.get("req_id", "")
        print(f"MQTT cmd: cmd={cmd} req_id={req_id} result=OK", flush=True)

    # ── 连接 ──────────────────────────────────────────────────

    def connect(self):
        """连接 MQTT broker。

        使用 connect_async() 避免阻塞 UI 启动 (03 §8.1)。
        连接建立后 on_connect 回调自动:
          - 订阅 cmd topic
          - 发布 status online (含当前 mode)
        """
        if not self.enabled:
            print("[MQTT] MQTT 已禁用 (MQTT_ENABLED=False)", flush=True)
            return

        self.client = mqtt.Client(
            client_id=self.device_id,
            protocol=mqtt.MQTTv311,
        )

        # Will: 异常断开时 Broker 代替发布 offline (03 §5.3.1)
        will_payload = json.dumps(
            {"device_id": self.device_id, "state": "offline"},
            ensure_ascii=False,
        )
        self.client.will_set(self.topic_status, will_payload, qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.message_callback_add(self.topic_cmd, self._on_cmd_message)

        # connect_async + loop_start: 后台连接，不阻塞 (03 §8.1)
        self.client.connect_async(self.host, self.port, keepalive=self.keepalive)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        """连接建立回调。

        subscribe 和 status publish 在此执行，因为 connect_async 返回时连接尚未就绪。
        """
        if rc == 0:
            self.connected = True
            print(f"[MQTT] 已连接 broker {self.host}:{self.port}", flush=True)

            # subscribe cmd topic (03 §8.1)
            client.subscribe(self.topic_cmd, qos=1)

            # 自动发布 status online (03 §8.1)
            self.publish_status("online", self._mode)
        else:
            print(f"[MQTT] 连接失败 rc={rc}", file=sys.stderr, flush=True)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            print(f"[MQTT] 异常断开 rc={rc}，paho 将自动重连",
                  file=sys.stderr, flush=True)

    def _on_cmd_message(self, client, userdata, msg):
        """cmd topic 消息处理。"""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"[MQTT] cmd 解析失败: {exc}", file=sys.stderr, flush=True)
            return
        self._cmd_callback(msg.topic, payload)

    # ── 模式设置 ──────────────────────────────────────────────

    def set_mode(self, mode: str):
        """设置当前运行模式，用于 on_connect 时自动发布的 status。"""
        self._mode = mode

    # ── 发布 status (03 §5.3.1) ──────────────────────────────

    def publish_status(self, state: str, mode: str = ""):
        """发布设备在线/离线状态。

        Args:
            state: "online" 或 "offline"
            mode: state="online" 时必须传入 "live" 或 "replay"

        Returns:
            MQTTMessageInfo | None — 可调用 .wait_for_publish(timeout) 等待确认

        QoS 1, retain true (03 §5.2.3)。
        """
        if not self.connected or self.client is None:
            return None

        if state == "online":
            payload = {
                "device_id": self.device_id,
                "state": "online",
                "mode": mode,
                "version": VERSION,
                "ts": int(time.time() * 1000),
            }
        else:
            payload = {
                "device_id": self.device_id,
                "state": "offline",
            }

        payload_json = json.dumps(payload, ensure_ascii=False)
        info = self.client.publish(self.topic_status, payload_json, qos=1, retain=True)
        return info

    # ── 发布 telemetry (03 §5.3.2) ───────────────────────────

    def publish_telemetry(self, data: dict):
        """发布遥测数据。

        QoS 0 (周期性发布，允许丢帧) (03 §5.2.3)。
        调用方 (telemetry_builder) 负责构建符合 03 §5.3.2 的 payload。
        """
        if not self.connected or self.client is None:
            return
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(self.topic_telemetry, payload, qos=0)

    # ── 发布 alarm (03 §5.3.3) ──────────────────────────────

    def publish_alarm(self, data: dict):
        """发布告警。

        QoS 1 (告警不可丢失) (03 §5.2.3)。
        调用方 (alarm_detector) 负责仅在告警状态变更时调用。
        """
        if not self.connected or self.client is None:
            return
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(self.topic_alarm, payload, qos=1)

    # ── 订阅 cmd ────────────────────────────────────────────

    def subscribe_cmd(self, callback=None):
        """设置命令回调。

        callback 签名: callback(topic: str, payload: dict)
        connect() 时已自动订阅 cmd topic，此处仅替换回调函数。
        """
        if callback is not None:
            self._cmd_callback = callback

    # ── 断开 (03 §8.4) ──────────────────────────────────────

    def disconnect(self):
        """断开 MQTT 连接。

        1. 发布 status offline (QoS 1, retain)
        2. wait_for_publish 超时 1 秒，确保离线消息已送达 Broker (03 §8.4)
        3. 停止后台 loop
        4. 断开连接
        """
        if self.client is None:
            return

        if self.connected:
            # 正常关闭时主动发布 offline，will 不触发 (03 §8.4)
            info = self.publish_status("offline")
            if info is not None:
                info.wait_for_publish(timeout=1.0)

        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False

    def close(self):
        """输出适配器统一关闭入口。"""
        self.disconnect()
