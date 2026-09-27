"""输入层模块。

从 can_recv4.py 中拆分出来的输入层，包含：
- 常量：DEFAULT_FALLBACK_STEP_US
- CSV 解析辅助：iso_to_unix_us, parse_int, parse_float
- open_bus: 打开 socketcan 总线
- CsvReplaySource: CSV 回放数据源（含时间轴索引）

本轮 (Prompt 4) 只拆 input 层，不涉及 core / output / MQTT / UI。
供 UI 层调解的串口输入接口在模块底部以注释形式预留。
"""

import csv
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path

from can_parser import LidarPoint, compute_xy_mm

# ── 常量 ────────────────────────────────────────────────────────

DEFAULT_FALLBACK_STEP_US = 10_000


# ── USB backend helpers ───────────────────────────────────────────────

def _configure_gs_usb_backend():
    """让 gs_usb 在 Windows 上优先使用 libusb-package 提供的 PyUSB backend。"""
    try:
        import libusb_package
        import usb.core
    except ModuleNotFoundError:
        return

    backend = libusb_package.get_libusb1_backend()
    if backend is None or getattr(usb.core.find, "_ladar2_backend_patch", False):
        return

    original_find = usb.core.find

    def find_with_libusb_backend(*args, **kwargs):
        if "backend" not in kwargs:
            kwargs["backend"] = backend
        return original_find(*args, **kwargs)

    find_with_libusb_backend._ladar2_backend_patch = True
    usb.core.find = find_with_libusb_backend


# ── CSV 解析辅助 ────────────────────────────────────────────────

def iso_to_unix_us(value):
    """ISO 8601 时间字符串 → UNIX 微秒。解析失败或为空时返回 None。"""
    value = (value or "").strip()
    if not value:
        return None
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000)


def parse_int(value, default=0):
    """安全解析整数，解析失败或为空时返回 default。"""
    text = (value or "").strip()
    if not text:
        return default
    return int(text)


def parse_float(value, default=0.0):
    """安全解析浮点数，解析失败或为空时返回 default。"""
    text = (value or "").strip()
    if not text:
        return default
    return float(text)


# ── CAN 总线输入 ────────────────────────────────────────────────

def open_bus(channel, interface=None, bitrate=None):
    """打开 python-can 总线。

    注：import can 放在函数内部（惰性导入），因为 can_input 模块在 can_recv4
    设置 venv 路径之前就会被导入。到 main() 调用 open_bus 时 venv 已就绪。

    Linux 默认保持原行为：未指定 interface 时使用 socketcan。
    Windows 必须显式指定 python-can backend，例如 virtual、pcan、kvaser、vector、slcan。
    """
    import can

    if interface is None:
        if not sys.platform.startswith("win"):
            interface = "socketcan"
        else:
            raise RuntimeError(
                "Windows live CAN 需要显式指定 --can-interface，例如 virtual、pcan、kvaser、vector 或 slcan；"
                "无硬件测试可用: --can-interface virtual --channel ladar2_virtual。"
            )

    if interface == "gs_usb":
        _configure_gs_usb_backend()
        if isinstance(channel, str) and channel.isdigit():
            channel = int(channel)

    kwargs = {"interface": interface, "channel": channel}
    if bitrate is not None:
        kwargs["bitrate"] = bitrate

    try:
        return can.Bus(**kwargs)
    except PermissionError as exc:
        raise RuntimeError(
            f"无法打开 {channel}: 当前权限不足。请检查 CAN 设备权限或驱动配置。"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"无法打开 {interface}/{channel}: {exc}") from exc


# ── CSV 回放数据源 ──────────────────────────────────────────────

class CsvReplaySource:
    """CSV 回放数据源。

    从 CSV 文件加载点云数据，提供时间轴驱动的点查询接口。
    支持正式格式（FORMAL_CSV_FIELDS）和旧版格式（LEGACY_CSV_FIELDS）的自动识别。
    """

    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.points = []
        self.timeline_us = []
        self.duration_us = 0
        self.summary_stats = self._load_summary()
        self._load_points()
        self._closed = False

    def close(self):
        """释放资源 (回放源无需关闭底层句柄，标记关闭状态)。"""
        self._closed = True

    @property
    def source_name(self):
        """可读来源标识，供 UI 面板使用。"""
        return str(self.csv_path)

    @property
    def mode(self):
        """运行模式固定为 "replay"。"""
        return "replay"

    def _load_summary(self):
        summary_path = self.csv_path.with_name(f"{self.csv_path.stem}_summary.txt")
        if not summary_path.exists():
            return {}

        stats = {}
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            stats[key.strip()] = value.strip()
        return stats

    def _load_points(self):
        with self.csv_path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise RuntimeError(f"CSV 缺少表头: {self.csv_path}")
            rows = list(reader)

        parsed_points = []
        time_candidates = []
        for index, row in enumerate(rows):
            if "host_rx_time_us" in row:
                point, time_candidate = self._parse_formal_row(row, index)
            else:
                point, time_candidate = self._parse_legacy_row(row, index)
            parsed_points.append(point)
            time_candidates.append(time_candidate)

        if not parsed_points:
            return

        base_time_us = time_candidates[0]
        previous_timeline = 0
        for index, point in enumerate(parsed_points):
            candidate = time_candidates[index]
            if base_time_us is None:
                timeline_us = index * DEFAULT_FALLBACK_STEP_US
            else:
                timeline_us = max(0, int(candidate - base_time_us))
            if index > 0 and timeline_us < previous_timeline:
                timeline_us = previous_timeline
            point.timeline_us = timeline_us
            self.points.append(point)
            self.timeline_us.append(timeline_us)
            previous_timeline = timeline_us

        self.duration_us = self.timeline_us[-1]

    def _parse_formal_row(self, row, index):
        host_rx_time_us = parse_int(row.get("host_rx_time_us"))
        point = LidarPoint(
            host_rx_time_us=host_rx_time_us,
            t_sample_us=parse_int(row.get("t_sample_us")),
            angle_tick=parse_int(row.get("angle_tick")),
            angle_deg=parse_float(row.get("angle_deg")),
            distance_cm=parse_int(row.get("distance_cm")),
            x_mm=parse_float(row.get("x_mm")),
            y_mm=parse_float(row.get("y_mm")),
            quality=parse_int(row.get("quality")),
            status=parse_int(row.get("status")),
            seq=None,
        )
        if not row.get("x_mm") or not row.get("y_mm"):
            point.x_mm, point.y_mm = compute_xy_mm(point.distance_cm, point.angle_deg)
        timeline_candidate = host_rx_time_us or (index * DEFAULT_FALLBACK_STEP_US)
        return point, timeline_candidate

    def _parse_legacy_row(self, row, index):
        parsed_host_time_us = iso_to_unix_us(row.get("host_time"))
        elapsed_us = None
        if (row.get("elapsed_s") or "").strip():
            elapsed_us = int(round(parse_float(row.get("elapsed_s")) * 1_000_000))

        point = LidarPoint.from_measurement(
            host_rx_time_us=parsed_host_time_us or 0,
            t_sample_us=parse_int(row.get("t_sample_us")),
            angle_tick=parse_int(row.get("angle_tick")),
            angle_deg=parse_float(row.get("angle_deg")),
            distance_cm=parse_int(row.get("distance_cm")),
            quality=parse_int(row.get("quality")),
            status=parse_int(row.get("status")),
            seq=parse_int(row.get("seq"), default=0),
        )

        if parsed_host_time_us is not None:
            timeline_candidate = parsed_host_time_us
        elif elapsed_us is not None:
            timeline_candidate = elapsed_us
        else:
            timeline_candidate = index * DEFAULT_FALLBACK_STEP_US

        return point, timeline_candidate

    def visible_points(self, current_time_us, history_window_us):
        """返回 (current_time_us - history_window_us, current_time_us] 区间内的点。"""
        if not self.points:
            return []
        left_time_us = max(0, current_time_us - history_window_us)
        left_index = bisect_left(self.timeline_us, left_time_us)
        right_index = bisect_right(self.timeline_us, current_time_us)
        return self.points[left_index:right_index]

    def latest_point(self, current_time_us):
        """返回 timeline_us ≤ current_time_us 的最后一个点。"""
        if not self.points:
            return None
        index = bisect_right(self.timeline_us, current_time_us) - 1
        if index < 0:
            return None
        return self.points[index]

    def summary_text(self):
        """返回回放摘要可读文本。"""
        if not self.summary_stats:
            return "回放模式：无配套 summary"
        return (
            f"ok={self.summary_stats.get('reassembly_ok_point_cnt', 'N/A')}  "
            f"timeout={self.summary_stats.get('reassembly_timeout_point_cnt', 'N/A')}  "
            f"overwrite_a={self.summary_stats.get('reassembly_overwrite_a_cnt', 'N/A')}  "
            f"overwrite_b={self.summary_stats.get('reassembly_overwrite_b_cnt', 'N/A')}  "
            f"pending={self.summary_stats.get('pending_frame_cnt', 'N/A')}"
        )

    def stats_snapshot(self):
        """返回重组统计快照 dict (与 CanPointAssembler.stats_snapshot 格式一致)。

        若无 summary_stats 则返回全零默认值。
        """
        if not self.summary_stats:
            return {"ok": 0, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 0}
        return {
            "ok": self.summary_stats.get("reassembly_ok_point_cnt", 0),
            "timeout": self.summary_stats.get("reassembly_timeout_point_cnt", 0),
            "overwrite_a": self.summary_stats.get("reassembly_overwrite_a_cnt", 0),
            "overwrite_b": self.summary_stats.get("reassembly_overwrite_b_cnt", 0),
            "pending": self.summary_stats.get("pending_frame_cnt", 0),
        }


# ── 输入源统一接口 (InputAdapter) ──────────────────────────────

class InputAdapter:
    """输入源统一基类 / 最小协议。

    所有输入源 (CAN live / CSV replay / serial) 至少提供:
      - close()         释放资源
      - source_name     可读来源标识
      - mode            运行模式标识 ("live" / "replay" / "serial-reserved")

    CsvReplaySource 遵循此协议；open_bus() 返回的原生 can.Bus 作为 live
    模式的信源，由 can_recv4.py 通过 CanPointAssembler 桥接到统一流程。

    后续新增输入源时继承本类即可，不必修改 parser / core / output。
    """

    def close(self):
        """释放输入源资源。"""
        raise NotImplementedError

    @property
    def source_name(self):
        raise NotImplementedError

    @property
    def mode(self):
        raise NotImplementedError


# ── 串口输入预留 (SerialCanSource) ─────────────────────────────

class SerialCanSource(InputAdapter):
    """串口 CAN 输入源 — 当前为预留桩 (stub)，尚未实现真实串口读取。

    序列:
      1. 接收原始 CAN 帧 (例如通过 UART-USB 桥接读取 STM32 发出的数据)
      2. 将帧转换为与 open_bus() 兼容的 can.Message 格式
      3. 由主程序通过 CanPointAssembler 解析

    当前状态:
      - 类名、构造参数、方法签名已定义，符合 InputAdapter 协议。
      - read_frame() 抛出 NotImplementedError，表明功能未实现。
      - 不声称串口已完成；不纳入 M6.5 验收范围。
    """

    def __init__(self, port: str, baudrate: int = 115200):
        self._port = port
        self._baudrate = baudrate
        self._mode = "serial-reserved"

    def close(self):
        """释放串口资源 (当前为 no-op 桩)。"""
        pass

    @property
    def source_name(self):
        return f"serial://{self._port}@{self._baudrate}"

    @property
    def mode(self):
        return self._mode

    def read_frame(self):
        """读取一帧原始 CAN 数据，无数据时返回 None。

        Raises:
            NotImplementedError: 串口输入尚未实现。
        """
        raise NotImplementedError(
            "SerialCanSource.read_frame() 尚未实现。"
            "串口输入当前为预留桩，不纳入 M6.5 验收范围。"
        )
