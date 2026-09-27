"""输出层 (output) 模块。

从 can_recv4.py 中拆分出来的输出层，按适配器 (adapter) 模式组织：
- CsvOutputAdapter / CsvPointWriter: CSV 点云写入
- LogOutputAdapter: 控制台日志输出
- UiOutputAdapter: UI 渲染输出 (主体位于 can_recv4.py 的 PointCloudWindow)
- MqttOutput: MQTT 输出插件 (位于 can_mqtt.py)

所有 output adapter 的职责都是"消费点、summary、状态"，
不能反向修改 parser / input 协议。

ui_output (PointCloudWindow) 因体量大且与 PySide6/pyqtgraph 深度耦合，
本轮仍保留在 can_recv4.py 中，通过导入本模块的 CsvPointWriter 和格式化函数来消费。
build_default_csv_path 因依赖 __file__ 也保留在 can_recv4.py。
"""

import csv
from datetime import datetime
from pathlib import Path

from can_parser import FORMAL_CSV_FIELDS, REASSEMBLY_TIMEOUT_S


# ── 格式化工具 ──────────────────────────────────────────────────

def format_duration_us(duration_us):
    """微秒 → MM:SS.s 格式 (用于回放时间轴标签)。"""
    total_ms = max(0, int(duration_us / 1000))
    seconds, milliseconds = divmod(total_ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds // 100:d}"


def format_distance_mm(distance_mm):
    """毫米 → 可读距离字符串 (用于雷达量程环标签)。"""
    value = f"{distance_mm / 1000.0:.2f}".rstrip("0").rstrip(".")
    return f"{value} m"


# ── CSV 摘要生成 ────────────────────────────────────────────────

def summary_lines_from_stats(csv_path, stats):
    """从重组统计快照生成 CSV 配套 summary 文件内容。"""
    return [
        f"csv_path={csv_path}",
        f"generated_at={datetime.now().isoformat(timespec='seconds')}",
        f"reassembly_ok_point_cnt={stats['ok']}",
        f"reassembly_timeout_point_cnt={stats['timeout']}",
        f"reassembly_overwrite_a_cnt={stats['overwrite_a']}",
        f"reassembly_overwrite_b_cnt={stats['overwrite_b']}",
        f"pending_frame_cnt={stats['pending']}",
        f"reassembly_timeout_ms={int(REASSEMBLY_TIMEOUT_S * 1000)}",
    ]


# ── CSV 点云写入器 ──────────────────────────────────────────────

class CsvPointWriter:
    """正式格式 CSV 点云写入器。

    写入 FORMAT_CSV_FIELDS 表头，每点一行，flush 保证实时落盘。
    提供配套 summary 文件写入和资源释放。
    """

    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.summary_path = self.csv_path.with_name(f"{self.csv_path.stem}_summary.txt")
        self.csv_file = self.csv_path.open("w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(FORMAL_CSV_FIELDS)
        self.csv_file.flush()

    @property
    def adapter_name(self):
        return "csv"

    def write_point(self, point):
        """写入一个 LidarPoint 为一行 CSV。"""
        self.csv_writer.writerow(point.to_csv_row())
        self.csv_file.flush()

    def write_summary(self, stats):
        """写入重组统计摘要到配套 summary.txt。"""
        lines = summary_lines_from_stats(self.csv_path, stats)
        self.summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def close(self):
        """关闭 CSV 文件。"""
        self.csv_file.close()


# ── 输出适配器基类 ──────────────────────────────────────────────

class OutputAdapter:
    """输出适配器最小边界协议。

    所有 output adapter (CSV / log / MQTT / UI) 至少提供:
      - close()          释放资源
      - adapter_name     适配器标识 (如 "csv", "log", "mqtt", "ui")
    """

    def close(self):
        """释放适配器资源。"""
        raise NotImplementedError

    @property
    def adapter_name(self):
        raise NotImplementedError


# ── 日志输出适配器 ──────────────────────────────────────────────

class LogOutputAdapter(OutputAdapter):
    """控制台日志输出适配器。

    消费设备状态汇总 (compute_device_summary dict)，以结构化文本输出到控制台。
    不依赖 PySide6 / pyqtgraph / Paho / CSV 句柄。
    """

    def __init__(self):
        self._closed = False

    @property
    def adapter_name(self):
        return "log"

    def close(self):
        self._closed = True

    def emit_summary(self, summary: dict):
        """输出设备状态汇总到 stdout。

        Args:
            summary: compute_device_summary() 返回的 dict
        """
        if self._closed:
            return

        mode = summary.get("mode", "?")
        point_count = summary.get("point_count", 0)
        sweep_count = summary.get("sweep_point_count", 0)
        min_dist = summary.get("min_distance_cm")
        is_alert = summary.get("is_alert", False)
        alert_level = summary.get("alert_level", 0)

        sector_lines = []
        for sec in summary.get("sectors", []):
            d = sec.get("min_distance_cm")
            dist_str = f"{d}cm" if d is not None else "—"
            alert_str = f"Lv{sec['alert_level']}" if sec.get("alert_level", 0) > 0 else "OK"
            sector_lines.append(
                f"  {sec['name']:6s} pts={sec.get('point_count', 0):4d}  "
                f"min={dist_str:>6s}  alert={alert_str}"
            )

        alert_tag = f"ALERT Lv{alert_level}" if is_alert else "OK"
        min_tag = f"{min_dist}cm" if min_dist is not None else "—"

        print(
            f"[LOG] mode={mode}  points={point_count}  sweep={sweep_count}  "
            f"min_dist={min_tag}  alarm={alert_tag}",
            flush=True,
        )
        if sector_lines:
            print("\n".join(sector_lines), flush=True)
