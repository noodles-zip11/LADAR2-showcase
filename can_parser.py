"""CAN protocol parser module.

从 can_recv4.py 中拆分出来的解析层，包含：
- 协议常量 (CAN ID, 超时, CSV 字段定义)
- LidarPoint 统一点数据模型
- CanPointAssembler 双帧重组器
- compute_xy_mm 极坐标→直角坐标换算

本轮 (Prompt 3) 只拆 parser 层，不涉及 input / core / output / MQTT。
"""

import math
import struct
import time
from dataclasses import dataclass

# ── 协议常量 ────────────────────────────────────────────────────

FRAME_HEADER_ID = 0x123
FRAME_TAIL_ID = 0x124
REASSEMBLY_TIMEOUT_S = 0.050

FORMAL_CSV_FIELDS = [
    "host_rx_time_us",
    "t_sample_us",
    "angle_tick",
    "angle_deg",
    "distance_cm",
    "x_mm",
    "y_mm",
    "quality",
    "status",
]
LEGACY_CSV_FIELDS = [
    "host_time",
    "elapsed_s",
    "seq",
    "distance_cm",
    "angle_deg",
    "quality",
    "t_sample_us",
    "angle_tick",
    "status",
]


# ── 几何换算 ────────────────────────────────────────────────────

def compute_xy_mm(distance_cm, angle_deg):
    """极坐标 (距离cm, 角度deg) → 直角坐标 (x_mm, y_mm)。"""
    radius_mm = float(distance_cm) * 10.0
    theta_rad = math.radians(angle_deg)
    return radius_mm * math.cos(theta_rad), radius_mm * math.sin(theta_rad)


# ── 统一点数据模型 ──────────────────────────────────────────────

@dataclass(slots=True)
class LidarPoint:
    """解析层输出的统一点对象。

    字段语义严格遵循 spec_freeze/02_字段表.md：
    - host_rx_time_us: 主机收到 header 帧时的 UNIX 微秒时间戳
    - t_sample_us:    MCU 采样时刻 (MCU 内部微秒)
    - angle_tick:     角度 tick 值 (MCU 原始值)
    - angle_deg:      角度 (度, 来自 header 帧 float32)
    - distance_cm:    距离 (厘米, 来自 header 帧 uint16)
    - quality:        信号质量 (0-255)
    - status:         状态字 (bit7=estimated, bit[2:0]=alert_level)
    - seq:            CAN 帧序号 (0-255, 仅内部使用)
    - x_mm / y_mm:    直角坐标 (毫米, 由 compute_xy_mm 派生)
    """

    host_rx_time_us: int
    t_sample_us: int
    angle_tick: int
    angle_deg: float
    distance_cm: int
    x_mm: float
    y_mm: float
    quality: int
    status: int
    seq: int | None = None
    timeline_us: int = 0

    @classmethod
    def from_measurement(
        cls,
        *,
        host_rx_time_us,
        t_sample_us,
        angle_tick,
        angle_deg,
        distance_cm,
        quality,
        status,
        seq=None,
    ):
        """从 CAN 双帧解析出的原始字段构造点对象。自动派生 x_mm / y_mm。"""
        x_mm, y_mm = compute_xy_mm(distance_cm, angle_deg)
        return cls(
            host_rx_time_us=int(host_rx_time_us),
            t_sample_us=int(t_sample_us),
            angle_tick=int(angle_tick),
            angle_deg=float(angle_deg),
            distance_cm=int(distance_cm),
            x_mm=float(x_mm),
            y_mm=float(y_mm),
            quality=int(quality),
            status=int(status),
            seq=seq,
        )

    def to_csv_row(self):
        """序列化为正式 CSV 行 (FORMAL_CSV_FIELDS 顺序)。"""
        return [
            self.host_rx_time_us,
            self.t_sample_us,
            self.angle_tick,
            f"{self.angle_deg:.6f}",
            self.distance_cm,
            f"{self.x_mm:.3f}",
            f"{self.y_mm:.3f}",
            self.quality,
            self.status,
        ]


# ── 双帧重组器 ──────────────────────────────────────────────────

class CanPointAssembler:
    """CAN 双帧 (0x123 header + 0x124 tail) 重组器。

    职责：
    - 接收原始 CAN 帧，按 seq 配对 header/tail
    - 配对完成后构造 LidarPoint
    - 超时清理未配对的半帧
    - 统计 ok / timeout / overwrite_a / overwrite_b / pending
    """

    def __init__(self, timeout_s=REASSEMBLY_TIMEOUT_S):
        self.timeout_s = timeout_s
        self.pending_frames = {}
        self.ok_count = 0
        self.timeout_count = 0
        self.overwrite_a_count = 0
        self.overwrite_b_count = 0

    def process_message(self, msg):
        """处理一条 CAN 消息。

        Returns:
            list[LidarPoint]: 如果该消息完成了双帧配对则返回 [point]，否则返回 []。
        """
        if len(msg.data) < 8:
            return []

        if msg.arbitration_id not in (FRAME_HEADER_ID, FRAME_TAIL_ID):
            return []

        now_monotonic = time.monotonic()
        seq = msg.data[0]
        frame = self.pending_frames.get(seq)
        if frame is None:
            frame = {
                "first_rx_monotonic": now_monotonic,
                "last_rx_monotonic": now_monotonic,
                "has_header": False,
                "has_tail": False,
            }
            self.pending_frames[seq] = frame
        else:
            frame["last_rx_monotonic"] = now_monotonic

        if msg.arbitration_id == FRAME_HEADER_ID:
            if frame["has_header"]:
                self.overwrite_a_count += 1
            frame["header"] = {
                "distance_cm": (msg.data[1] << 8) | msg.data[2],
                "angle_deg": struct.unpack(">f", bytes(msg.data[3:7]))[0],
                "quality": msg.data[7],
            }
            frame["has_header"] = True
        elif msg.arbitration_id == FRAME_TAIL_ID:
            if frame["has_tail"]:
                self.overwrite_b_count += 1
            frame["tail"] = {
                "t_sample_us": int.from_bytes(msg.data[1:5], byteorder="big"),
                "angle_tick": int.from_bytes(msg.data[5:7], byteorder="big"),
                "status": msg.data[7],
            }
            frame["has_tail"] = True

        point = self._try_commit_frame(seq)
        return [point] if point is not None else []

    def _try_commit_frame(self, seq):
        """检查 seq 对应的帧是否 header+tail 齐全，是则构造 LidarPoint 并清理。"""
        frame = self.pending_frames.get(seq)
        if frame is None or not (frame["has_header"] and frame["has_tail"]):
            return None

        header = frame["header"]
        tail = frame["tail"]
        point = LidarPoint.from_measurement(
            host_rx_time_us=time.time_ns() // 1000,
            t_sample_us=tail["t_sample_us"],
            angle_tick=tail["angle_tick"],
            angle_deg=header["angle_deg"],
            distance_cm=header["distance_cm"],
            quality=header["quality"],
            status=tail["status"],
            seq=seq,
        )
        self.pending_frames.pop(seq, None)
        self.ok_count += 1
        return point

    def prune_stale_frames(self):
        """清理超过 timeout_s 仍未配对的半帧。"""
        now_monotonic = time.monotonic()
        stale_seqs = [
            seq
            for seq, frame in self.pending_frames.items()
            if now_monotonic - frame["first_rx_monotonic"] > self.timeout_s
        ]
        for seq in stale_seqs:
            self.timeout_count += 1
            frame = self.pending_frames.pop(seq, None)
            if frame is None:
                continue
            age_ms = (now_monotonic - frame["first_rx_monotonic"]) * 1000.0
            print(
                "timeout "
                f"seq={seq} has_header={int(frame['has_header'])} "
                f"has_tail={int(frame['has_tail'])} age_ms={age_ms:.1f}",
                flush=True,
            )

    def stats_snapshot(self):
        """返回重组统计快照 (dict)，供 CSV summary 和状态面板使用。"""
        return {
            "ok": self.ok_count,
            "timeout": self.timeout_count,
            "overwrite_a": self.overwrite_a_count,
            "overwrite_b": self.overwrite_b_count,
            "pending": len(self.pending_frames),
        }

    def stats_text(self):
        """返回人类可读的重组统计字符串。"""
        stats = self.stats_snapshot()
        return (
            f"ok={stats['ok']}  timeout={stats['timeout']}  "
            f"overwrite_a={stats['overwrite_a']}  overwrite_b={stats['overwrite_b']}  "
            f"pending={stats['pending']}"
        )
