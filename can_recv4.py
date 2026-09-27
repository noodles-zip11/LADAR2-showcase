#!LOCAL_HOME_1/can-venv/bin/python
import argparse
import math
import os
import signal
import sys
import time
from bisect import bisect_right
from collections import deque
from datetime import datetime
from pathlib import Path

from can_parser import (
    CanPointAssembler,
    LidarPoint,
    compute_xy_mm,
    FORMAL_CSV_FIELDS,
    FRAME_HEADER_ID,
    FRAME_TAIL_ID,
    LEGACY_CSV_FIELDS,
    REASSEMBLY_TIMEOUT_S,
)

from can_input import (
    CsvReplaySource,
    DEFAULT_FALLBACK_STEP_US,
    iso_to_unix_us,
    open_bus,
    parse_float,
    parse_int,
)

from can_core import (
    DERIVED_ALARM_CLEAR_CM,
    DERIVED_ALARM_NEAR_CM,
    DERIVED_ALARM_TOO_NEAR_CM,
    DERIVED_ALARM_WINDOW_MS,
    DERIVED_NO_POINTS_MS,
    DERIVED_STARTUP_GRACE_MS,
    MIN_SWEEP_POINT_COUNT,
    STATUS_ALERT_MASK,
    STATUS_ESTIMATED,
    SWEEP_BREAK_DISTANCE_MM,
    SWEEP_TARGET_DEG,
    alarm_state_changed,
    angular_delta_deg,
    build_sweep_curve,
    build_telemetry_dict,
    compute_alarm_state,
    compute_derived_alarm_state,
    compute_device_summary,
    compute_min_distance,
    compute_sector_summary,
    extract_recent_sweep,
)

from can_output import (
    CsvPointWriter,
    format_distance_mm,
    format_duration_us,
    LogOutputAdapter,
    summary_lines_from_stats,
)

from can_mqtt import CmdDispatcher, MqttOutput

LIVE_POLL_INTERVAL_MS = 10
LIVE_RECV_TIMEOUT_S = 0.001
RENDER_INTERVAL_MS = 33
REPLAY_INTERVAL_MS = 16
HISTORY_WINDOW_US = 8_000_000
MIN_AUTO_RANGE_MM = 500.0
AUTO_RANGE_PADDING = 1.18


def add_local_venv_to_sys_path():
    venv_site = (
        Path(__file__).resolve().parent
        / "can-venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if venv_site.exists():
        sys.path.insert(0, str(venv_site))


try:
    import can
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError:
    add_local_venv_to_sys_path()
    import can
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets




def build_default_csv_path():
    return Path(__file__).resolve().with_name(
        f"can_distance_{datetime.now():%Y%m%d_%H%M%S}.csv"
    )


class PointCloudWindow(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        mode,
        channel,
        replay_speed,
        bus=None,
        csv_writer=None,
        replay_csv_path=None,
        mqtt_output=None,
    ):
        super().__init__()
        self.mode = mode
        self.channel = channel
        self.bus = bus
        self.csv_writer = csv_writer
        self.mqtt_output = mqtt_output
        self.assembler = CanPointAssembler() if mode == "live" else None
        self.live_points = deque()
        self.latest_point = None
        self.render_times = deque(maxlen=120)
        self.closed = False
        self.last_range_mm = None

        # 日志输出适配器 (节流: 每 2 秒输出一次设备状态)
        self._log_output = LogOutputAdapter()
        self._log_output_last_s = 0.0

        # MQTT 发布节流与告警状态跟踪
        self._mqtt_last_telemetry_s = 0.0
        self._mqtt_last_alarm_state = None
        self._last_sweep_points = []
        self._alarm_window_points = deque()  # 最近 ~500ms 的点 (派生距离告警用)
        self._last_live_point_time_ms = None  # 上一个 live 点的 wall-clock ms
        self._last_alarm_point_payload = None  # 缓存最后一个点的摘要 (无点告警也需要 latest_point)

        self.replay_source = None
        self.replay_current_us = 0
        self.replay_last_tick_monotonic = time.monotonic()
        self.replay_playing = False
        self.replay_was_playing_before_seek = False
        self._replay_last_alarm_time_us = -1
        self.user_is_scrubbing = False
        self.replay_speed = replay_speed

        self.setWindowTitle("2D LiDAR 点云台")
        self.resize(1420, 920)
        self._build_ui()
        self._configure_plot()

        self.render_timer = QtCore.QTimer(self)
        self.render_timer.timeout.connect(self.render_scene)
        self.render_timer.start(RENDER_INTERVAL_MS)

        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.timeout.connect(self.poll_live_bus)
        if self.mode == "live":
            self.poll_timer.start(LIVE_POLL_INTERVAL_MS)

        self.replay_timer = QtCore.QTimer(self)
        self.replay_timer.timeout.connect(self.advance_replay)
        self.replay_timer.start(REPLAY_INTERVAL_MS)

        if replay_csv_path is not None:
            self.load_replay_source(replay_csv_path)

        self.update_mode_widgets()
        self.refresh_status_labels()
        self.render_scene()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #eef3f8;
                color: #13263d;
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
            }
            QFrame#card {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(16, 35, 58, 0.08);
                border-radius: 20px;
            }
            QFrame#radarCard {
                background: #071a2b;
                border: 1px solid rgba(111, 221, 255, 0.22);
                border-radius: 24px;
            }
            QLabel#title {
                font-size: 26px;
                font-weight: 700;
                color: #0c2138;
            }
            QLabel#subtitle {
                font-size: 13px;
                color: #5a728f;
            }
            QLabel#metricLabel {
                padding: 8px 12px;
                background: rgba(13, 35, 58, 0.06);
                border-radius: 12px;
                font-weight: 600;
            }
            QLabel#controlTitle {
                font-size: 14px;
                font-weight: 700;
                color: #0e2740;
            }
            QLabel#hint {
                color: #5f7590;
            }
            QLabel#alarmClear {
                padding: 8px 12px;
                background: rgba(0, 180, 100, 0.12);
                border: 1px solid rgba(0, 180, 100, 0.25);
                border-radius: 12px;
                font-weight: 600;
                color: #007a3d;
            }
            QLabel#alarmActive {
                padding: 8px 12px;
                background: rgba(220, 50, 50, 0.12);
                border: 1px solid rgba(220, 50, 50, 0.30);
                border-radius: 12px;
                font-weight: 700;
                color: #b71c1c;
            }
            QLabel#panelSection {
                font-size: 12px;
                font-weight: 700;
                color: #5a728f;
                margin-top: 8px;
            }
            QLabel#panelValue {
                font-size: 13px;
                color: #13263d;
            }
            QPushButton {
                min-height: 36px;
                padding: 0 14px;
                border-radius: 10px;
                border: 1px solid rgba(12, 44, 74, 0.12);
                background: #ffffff;
            }
            QPushButton:hover {
                background: #edf8ff;
            }
            QPushButton#primary {
                background: #0e4969;
                color: #f3fbff;
                border: 1px solid #0e4969;
            }
            QPushButton#primary:hover {
                background: #116084;
            }
            QComboBox, QSlider {
                min-height: 34px;
            }
            QComboBox {
                background: #ffffff;
                border: 1px solid rgba(12, 44, 74, 0.12);
                border-radius: 10px;
                padding: 0 10px;
            }
            """
        )

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(16)

        header_card = QtWidgets.QFrame(objectName="card")
        header_layout = QtWidgets.QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(10)

        title_row = QtWidgets.QHBoxLayout()
        title_column = QtWidgets.QVBoxLayout()
        title_column.setSpacing(2)
        title_label = QtWidgets.QLabel("2D LiDAR 点云台", objectName="title")
        subtitle_label = QtWidgets.QLabel(
            "实时 CAN 接收与 CSV 回放共用同一套点云视图、时间轴和重组统计。", objectName="subtitle"
        )
        title_column.addWidget(title_label)
        title_column.addWidget(subtitle_label)
        title_row.addLayout(title_column)
        title_row.addStretch(1)

        self.mode_metric = QtWidgets.QLabel(objectName="metricLabel")
        self.points_metric = QtWidgets.QLabel(objectName="metricLabel")
        self.fps_metric = QtWidgets.QLabel(objectName="metricLabel")
        self.reassembly_metric = QtWidgets.QLabel(objectName="metricLabel")
        self.mqtt_metric = QtWidgets.QLabel(objectName="metricLabel")
        self.alarm_metric = QtWidgets.QLabel(objectName="metricLabel")
        for widget in (
            self.mode_metric,
            self.points_metric,
            self.fps_metric,
            self.reassembly_metric,
            self.mqtt_metric,
            self.alarm_metric,
        ):
            title_row.addWidget(widget)

        header_layout.addLayout(title_row)

        self.current_point_label = QtWidgets.QLabel("当前点: 等待数据...", objectName="hint")
        self.source_label = QtWidgets.QLabel("数据源: 未初始化", objectName="hint")
        header_layout.addWidget(self.current_point_label)
        header_layout.addWidget(self.source_label)
        outer_layout.addWidget(header_card)

        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(16)
        outer_layout.addLayout(content_layout, 1)

        radar_card = QtWidgets.QFrame(objectName="radarCard")
        radar_layout = QtWidgets.QVBoxLayout(radar_card)
        radar_layout.setContentsMargins(18, 18, 18, 18)
        radar_layout.setSpacing(10)

        self.plot_widget = pg.PlotWidget()
        radar_layout.addWidget(self.plot_widget, 1)

        self.radar_hint_label = QtWidgets.QLabel(
            "显示策略：最近 8 秒散点做背景，最近一圈扫描用轮廓线强调；最新点更亮，异常状态以橙红高亮。"
        )
        self.radar_hint_label.setStyleSheet("color: #a8d8ff; background: transparent;")
        radar_layout.addWidget(self.radar_hint_label)
        content_layout.addWidget(radar_card, 1)

        control_card = QtWidgets.QFrame(objectName="card")
        control_card.setFixedWidth(320)
        control_layout = QtWidgets.QVBoxLayout(control_card)
        control_layout.setContentsMargins(18, 18, 18, 18)
        control_layout.setSpacing(14)

        mode_title = QtWidgets.QLabel("控制面板", objectName="controlTitle")
        control_layout.addWidget(mode_title)

        self.mode_label = QtWidgets.QLabel()
        self.mode_label.setWordWrap(True)
        control_layout.addWidget(self.mode_label)

        self.source_path_label = QtWidgets.QLabel()
        self.source_path_label.setWordWrap(True)
        self.source_path_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard
        )
        control_layout.addWidget(self.source_path_label)

        self.output_path_label = QtWidgets.QLabel()
        self.output_path_label.setWordWrap(True)
        self.output_path_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard
        )
        control_layout.addWidget(self.output_path_label)

        self.choose_csv_button = QtWidgets.QPushButton("选择回放 CSV")
        self.choose_csv_button.clicked.connect(self.choose_replay_csv)
        control_layout.addWidget(self.choose_csv_button)

        self.play_pause_button = QtWidgets.QPushButton("暂停回放")
        self.play_pause_button.setObjectName("primary")
        self.play_pause_button.clicked.connect(self.toggle_playback)
        control_layout.addWidget(self.play_pause_button)

        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x"])
        self.speed_combo.setCurrentText(f"{self.replay_speed:g}x")
        self.speed_combo.currentTextChanged.connect(self.change_replay_speed)
        control_layout.addWidget(QtWidgets.QLabel("回放速度"))
        control_layout.addWidget(self.speed_combo)

        self.range_combo = QtWidgets.QComboBox()
        self.range_combo.addItems(["Auto", "0.5m", "1m", "2m"])
        self.range_combo.setCurrentText("Auto")
        self.range_combo.currentTextChanged.connect(self.render_scene)
        control_layout.addWidget(QtWidgets.QLabel("雷达量程"))
        control_layout.addWidget(self.range_combo)

        self.reset_view_button = QtWidgets.QPushButton("重置视图")
        self.reset_view_button.clicked.connect(self.reset_view)
        control_layout.addWidget(self.reset_view_button)

        # ── 扇区摘要 ───────────────────────────────────────────
        sector_title = QtWidgets.QLabel("扇区摘要", objectName="panelSection")
        control_layout.addWidget(sector_title)

        self.sector_panel_label = QtWidgets.QLabel()
        self.sector_panel_label.setWordWrap(True)
        self.sector_panel_label.setStyleSheet(
            "padding: 8px 12px; border-radius: 12px; background: rgba(14, 39, 64, 0.04);"
            "font-size: 12px;"
        )
        control_layout.addWidget(self.sector_panel_label)

        # ── 状态面板 ───────────────────────────────────────────
        status_title = QtWidgets.QLabel("状态面板", objectName="panelSection")
        control_layout.addWidget(status_title)

        self.status_panel_label = QtWidgets.QLabel()
        self.status_panel_label.setWordWrap(True)
        self.status_panel_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.status_panel_label.setStyleSheet(
            "padding: 12px; border-radius: 14px; background: rgba(14, 39, 64, 0.05);"
        )
        control_layout.addWidget(self.status_panel_label, 1)

        control_layout.addStretch(1)
        content_layout.addWidget(control_card, 0)

        self.timeline_card = QtWidgets.QFrame(objectName="card")
        timeline_layout = QtWidgets.QVBoxLayout(self.timeline_card)
        timeline_layout.setContentsMargins(18, 14, 18, 14)
        timeline_layout.setSpacing(10)
        timeline_title = QtWidgets.QLabel("回放时间轴", objectName="controlTitle")
        timeline_layout.addWidget(timeline_title)

        self.timeline_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.sliderPressed.connect(self.on_timeline_pressed)
        self.timeline_slider.sliderReleased.connect(self.on_timeline_released)
        self.timeline_slider.valueChanged.connect(self.on_timeline_changed)
        timeline_layout.addWidget(self.timeline_slider)

        self.timeline_label = QtWidgets.QLabel("00:00.0 / 00:00.0")
        timeline_layout.addWidget(self.timeline_label)
        outer_layout.addWidget(self.timeline_card)

    def _configure_plot(self):
        pg.setConfigOptions(antialias=True)
        plot_item = self.plot_widget.getPlotItem()
        plot_item.hideAxis("bottom")
        plot_item.hideAxis("left")
        plot_item.setMenuEnabled(False)
        plot_item.setMouseEnabled(x=True, y=True)
        self.plot_widget.setBackground("#071a2b")
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.showGrid(x=False, y=False)

        self.guide_items = []
        self.history_scatter = pg.ScatterPlotItem(pxMode=True)
        self.sweep_curve = pg.PlotDataItem(
            pen=pg.mkPen("#9ee8ff", width=2.4),
            antialias=True,
            connect="finite",
        )
        self.latest_scatter = pg.ScatterPlotItem(pxMode=True)
        plot_item.addItem(self.history_scatter)
        plot_item.addItem(self.sweep_curve)
        plot_item.addItem(self.latest_scatter)

    def reset_view(self):
        self.last_range_mm = None
        self.render_scene()

    def update_mode_widgets(self):
        is_replay = self.mode == "replay"
        self.timeline_card.setVisible(is_replay)
        self.choose_csv_button.setVisible(is_replay)
        self.play_pause_button.setVisible(is_replay)
        self.speed_combo.setVisible(is_replay)

        if is_replay:
            self.mode_label.setText("模式：CSV 回放")
            output_text = "输出文件：回放模式不写出 CSV"
        else:
            self.mode_label.setText(f"模式：实时 CAN 接收 ({self.channel})")
            output_text = f"输出文件：{self.csv_writer.csv_path}" if self.csv_writer else "输出文件：未配置"
        self.output_path_label.setText(output_text)

    def change_replay_speed(self, text):
        self.replay_speed = float(text.rstrip("x"))

    def choose_replay_csv(self):
        csv_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择回放 CSV",
            str(Path.cwd()),
            "CSV 文件 (*.csv)",
        )
        if csv_path:
            self.load_replay_source(csv_path)

    def load_replay_source(self, csv_path):
        try:
            self.replay_source = CsvReplaySource(csv_path)
        except Exception as exc:  # pragma: no cover - UI path
            QtWidgets.QMessageBox.critical(self, "加载失败", str(exc))
            return

        self.mode = "replay"
        self.replay_current_us = 0
        self.replay_last_tick_monotonic = time.monotonic()
        self.replay_playing = bool(self.replay_source.points)
        self._replay_last_alarm_time_us = -1
        self.play_pause_button.setText("暂停回放" if self.replay_playing else "开始回放")

        # MQTT: 模式切换时更新 status (03 §8.3)
        if self.mqtt_output is not None:
            self.mqtt_output.set_mode("replay")
            self.mqtt_output.publish_status("online", "replay")
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setRange(0, int(self.replay_source.duration_us / 1000))
        self.timeline_slider.setValue(0)
        self.timeline_slider.blockSignals(False)
        self.latest_point = None
        self.live_points.clear()
        self.last_range_mm = None
        self.update_mode_widgets()
        self.refresh_status_labels()
        self.render_scene()

    def toggle_playback(self):
        if self.mode != "replay" or self.replay_source is None:
            return
        self.replay_playing = not self.replay_playing
        self.replay_last_tick_monotonic = time.monotonic()
        self.play_pause_button.setText("暂停回放" if self.replay_playing else "继续回放")

    def on_timeline_pressed(self):
        if self.mode != "replay":
            return
        self.user_is_scrubbing = True
        self.replay_was_playing_before_seek = self.replay_playing
        self.replay_playing = False
        self.play_pause_button.setText("继续回放")

    def on_timeline_released(self):
        if self.mode != "replay":
            return
        self.user_is_scrubbing = False
        self.replay_playing = self.replay_was_playing_before_seek
        self.replay_last_tick_monotonic = time.monotonic()
        self.play_pause_button.setText("暂停回放" if self.replay_playing else "继续回放")

    def on_timeline_changed(self, slider_value):
        if self.mode != "replay" or self.replay_source is None:
            return
        self.replay_current_us = int(slider_value) * 1000
        self.render_scene()

    def poll_live_bus(self):
        if self.mode != "live" or self.bus is None:
            return

        got_points = False
        while True:
            message = self.bus.recv(timeout=LIVE_RECV_TIMEOUT_S)
            if message is None:
                break
            for point in self.assembler.process_message(message):
                self.ingest_live_point(point)
                got_points = True

        self.assembler.prune_stale_frames()

        # 无点超时检查：本轮没有新点且之前有过数据，传入 point=None
        if not got_points and self._last_live_point_time_ms is not None:
            self._check_and_publish_alarm(None)

        self.refresh_status_labels()

    def ingest_live_point(self, point):
        self.latest_point = point
        self.live_points.append(point)
        if self.csv_writer is not None:
            self.csv_writer.write_point(point)

        cutoff_us = point.host_rx_time_us - HISTORY_WINDOW_US
        while self.live_points and self.live_points[0].host_rx_time_us < cutoff_us:
            self.live_points.popleft()

        # 维护派生告警窗口 (最近 ~500ms)
        now_ms = int(time.time() * 1000)
        self._last_live_point_time_ms = now_ms
        self._alarm_window_points.append(point)
        alarm_cutoff_us = point.host_rx_time_us - DERIVED_ALARM_WINDOW_MS * 1000
        while (self._alarm_window_points
               and self._alarm_window_points[0].host_rx_time_us < alarm_cutoff_us):
            self._alarm_window_points.popleft()

        # 每个新点进入时立即检查告警 (03 §8.2 主检查入口)
        self._check_and_publish_alarm(point)

        print(
            f"{point.host_rx_time_us} seq={point.seq} distance={point.distance_cm}cm "
            f"angle={point.angle_deg:.2f}deg quality={point.quality} "
            f"t_sample_us={point.t_sample_us} angle_tick={point.angle_tick} "
            f"status=0x{point.status:02X}",
            flush=True,
        )

    def _alarm_window_for_point(self, point):
        """获取派生距离告警用的窗口点列表 (最近 ~500ms)。

        Live 模式使用 self._alarm_window_points (ingest_live_point 维护)。
        Replay 模式从 replay_source.timeline_us 用 bisect 切片。
        """
        if self.mode == "live":
            return list(self._alarm_window_points)

        # Replay: 从 replay_source 取 point.timeline_us 前 500ms 的点
        if point is None or self.replay_source is None:
            return []
        timeline = self.replay_source.timeline_us
        if not timeline:
            return [point]
        window_us = DERIVED_ALARM_WINDOW_MS * 1000
        cutoff_us = point.timeline_us - window_us
        start_idx = bisect_right(timeline, cutoff_us)
        end_idx = bisect_right(timeline, point.timeline_us)
        return self.replay_source.points[start_idx:end_idx] if start_idx < end_idx else [point]

    def _check_and_publish_alarm(self, point):
        """检查并发布告警状态变更 (03 §5.3.3, §8.2)。

        使用 can_core.compute_derived_alarm_state 计算综合告警状态，
        包含 MCU status 告警和派生距离/遮挡告警。
        仅在告警等级或原因变化时发布。

        Args:
            point: 当前最新 LidarPoint，或 None (无点超时检查时)
        """
        if self.mqtt_output is None or not self.mqtt_output.connected:
            return

        # 只要收到真实点就立即缓存，确保后续无点告警也有 latest_point
        if point is not None:
            self._last_alarm_point_payload = {
                "distance_cm": point.distance_cm,
                "angle_deg": point.angle_deg,
                "quality": point.quality,
                "status": point.status,
            }

        now_ms = int(time.time() * 1000)
        alarm_window = self._alarm_window_for_point(point) if point is not None else []

        state = compute_derived_alarm_state(
            current_point=point,
            alarm_window_points=alarm_window,
            previous_state=self._mqtt_last_alarm_state,
            now_ms=now_ms,
        )

        # 首个点不发布，仅记录初始状态
        if self._mqtt_last_alarm_state is None:
            self._mqtt_last_alarm_state = state
            return

        if not alarm_state_changed(state, self._mqtt_last_alarm_state):
            self._mqtt_last_alarm_state = state
            return

        self._mqtt_last_alarm_state = state
        alarm = {
            "device_id": self.mqtt_output.device_id,
            "ts": int(time.time() * 1000),
            "alarm": state["is_alert"],
            "alarm_status": state["alert_level"],
            "alarm_source": state["alarm_source"],
            "alarm_reason": state["alarm_reason"],
            "threshold_cm": state["threshold_cm"],
            "min_distance_cm": state["min_distance_cm"],
            "alarm_description": (
                f"{state['alarm_source']}: {state['alarm_reason']}"
                if state["is_alert"]
                else "alarm cleared"
            ),
        }
        # 写入 latest_point (无点告警也使用最后一个已知点)
        if self._last_alarm_point_payload is not None:
            alarm["latest_point"] = self._last_alarm_point_payload
        self.mqtt_output.publish_alarm(alarm)

    def advance_replay(self):
        if (
            self.mode != "replay"
            or self.replay_source is None
            or not self.replay_playing
            or not self.replay_source.points
        ):
            return

        now_monotonic = time.monotonic()
        delta_us = int(
            (now_monotonic - self.replay_last_tick_monotonic) * 1_000_000 * self.replay_speed
        )
        self.replay_last_tick_monotonic = now_monotonic
        self.replay_current_us = min(
            self.replay_source.duration_us,
            self.replay_current_us + max(delta_us, 0),
        )

        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(int(self.replay_current_us / 1000))
        self.timeline_slider.blockSignals(False)

        if self.replay_current_us >= self.replay_source.duration_us:
            self.replay_playing = False
            self.play_pause_button.setText("重新播放")

        # 回放路径: 遍历所有新出现的点做 alarm 检查 (Prompt 11)
        if self.replay_source is not None and self.replay_source.points:
            timeline = self.replay_source.timeline_us
            start_idx = bisect_right(timeline, self._replay_last_alarm_time_us)
            end_idx = bisect_right(timeline, self.replay_current_us)
            if start_idx <= end_idx:
                for i in range(start_idx, end_idx):
                    self._check_and_publish_alarm(self.replay_source.points[i])
            if end_idx > 0:
                self._replay_last_alarm_time_us = timeline[end_idx - 1]

        self.render_scene()

    def visible_points(self):
        if self.mode == "replay":
            if self.replay_source is None:
                return []
            return self.replay_source.visible_points(self.replay_current_us, HISTORY_WINDOW_US)
        return list(self.live_points)

    def current_status_point(self):
        if self.mode == "replay":
            if self.replay_source is None:
                return None
            return self.replay_source.latest_point(self.replay_current_us)
        return self.latest_point

    def resolve_range_mm(self, points):
        current_text = self.range_combo.currentText()
        if current_text == "0.5m":
            return 500.0
        if current_text == "1m":
            return 1000.0
        if current_text == "2m":
            return 2000.0

        max_radius = MIN_AUTO_RANGE_MM
        for point in points:
            max_radius = max(max_radius, math.hypot(point.x_mm, point.y_mm))
        padded = max_radius * AUTO_RANGE_PADDING
        return max(MIN_AUTO_RANGE_MM, math.ceil(padded / 250.0) * 250.0)

    def rebuild_guides(self, range_mm):
        if self.last_range_mm == range_mm:
            return

        plot_item = self.plot_widget.getPlotItem()
        for item in self.guide_items:
            plot_item.removeItem(item)
        self.guide_items.clear()

        ring_pen = pg.mkPen("#245472", width=1.0)
        axis_pen = pg.mkPen("#4ca3c7", width=1.3)
        label_color = "#8dd8ff"

        self.guide_items.append(pg.InfiniteLine(pos=0, angle=0, pen=axis_pen))
        self.guide_items.append(pg.InfiniteLine(pos=0, angle=90, pen=axis_pen))
        for item in self.guide_items:
            plot_item.addItem(item)

        ring_factors = [0.25, 0.5, 0.75, 1.0]
        for factor in ring_factors:
            radius_mm = range_mm * factor
            points = []
            for degree in range(0, 361, 4):
                theta = math.radians(degree)
                points.append((radius_mm * math.cos(theta), radius_mm * math.sin(theta)))
            ring_item = pg.PlotDataItem(
                [x for x, _ in points],
                [y for _, y in points],
                pen=ring_pen,
            )
            plot_item.addItem(ring_item)
            self.guide_items.append(ring_item)

            label_item = pg.TextItem(
                text=format_distance_mm(radius_mm),
                color=label_color,
                anchor=(0, 1),
            )
            label_item.setPos(radius_mm * 0.04, radius_mm)
            plot_item.addItem(label_item)
            self.guide_items.append(label_item)

        for text, position in (
            ("Y+", (0, range_mm)),
            ("Y-", (0, -range_mm)),
            ("X+", (range_mm, 0)),
            ("X-", (-range_mm, 0)),
        ):
            text_item = pg.TextItem(text=text, color=label_color, anchor=(0.5, 0.5))
            text_item.setPos(*position)
            plot_item.addItem(text_item)
            self.guide_items.append(text_item)

        self.plot_widget.setXRange(-range_mm, range_mm, padding=0.02)
        self.plot_widget.setYRange(-range_mm, range_mm, padding=0.02)
        self.last_range_mm = range_mm

    def render_scene(self, *_args):
        visible_points = self.visible_points()
        current_point = self.current_status_point()

        range_mm = self.resolve_range_mm(visible_points)
        self.rebuild_guides(range_mm)

        if visible_points:
            if self.mode == "replay":
                current_time_us = self.replay_current_us
                age_at = lambda point: current_time_us - point.timeline_us
            else:
                current_time_us = visible_points[-1].host_rx_time_us
                age_at = lambda point: current_time_us - point.host_rx_time_us

            spots = []
            for point in visible_points:
                age_ratio = max(0.12, 1.0 - (age_at(point) / HISTORY_WINDOW_US))
                if point.status & STATUS_ALERT_MASK:
                    red = 255
                    green = int(92 + 80 * age_ratio)
                    blue = 68
                else:
                    red = 72
                    green = int(170 + 40 * age_ratio)
                    blue = 255
                alpha = int(28 + 112 * age_ratio)
                spots.append(
                    {
                        "pos": (point.x_mm, point.y_mm),
                        "data": point,
                        "brush": pg.mkBrush(red, green, blue, alpha),
                        "pen": pg.mkPen(0, 0, 0, 0),
                        "size": 4.0,
                    }
                )
            self.history_scatter.setData(spots)
        else:
            self.history_scatter.setData([])

        self._last_sweep_points = sweep_points = extract_recent_sweep(visible_points)
        if len(sweep_points) >= 2:
            sweep_xs, sweep_ys = build_sweep_curve(sweep_points)
            self.sweep_curve.setData(sweep_xs, sweep_ys)
        else:
            self.sweep_curve.setData([], [])

        if current_point is not None:
            self.latest_scatter.setData(
                [
                    {
                        "pos": (current_point.x_mm, current_point.y_mm),
                        "brush": pg.mkBrush(255, 255, 255, 255),
                        "pen": pg.mkPen("#7ef1ff", width=2),
                        "size": 13,
                    }
                ]
            )
        else:
            self.latest_scatter.setData([])

        if self.mode == "replay" and self.replay_source is not None:
            self.timeline_label.setText(
                f"{format_duration_us(self.replay_current_us)} / {format_duration_us(self.replay_source.duration_us)}"
            )

        self.refresh_status_labels()
        self.render_times.append(time.monotonic())

    def refresh_status_labels(self):
        visible_points = self.visible_points()
        current_point = self.current_status_point()

        fps = 0.0
        if len(self.render_times) >= 2:
            duration_s = self.render_times[-1] - self.render_times[0]
            if duration_s > 0:
                fps = (len(self.render_times) - 1) / duration_s

        # ── header 指标 ───────────────────────────────────────
        self.mode_metric.setText("模式  实时接收" if self.mode == "live" else "模式  CSV 回放")
        self.points_metric.setText(f"点数  {len(visible_points)}")
        self.fps_metric.setText(f"刷新 FPS  {fps:4.1f}")

        if self.mode == "live" and self.assembler is not None:
            reassembly_text = self.assembler.stats_text()
        elif self.replay_source is not None:
            reassembly_text = self.replay_source.summary_text()
        else:
            reassembly_text = "回放模式：尚未加载 CSV"
        self.reassembly_metric.setText(f"重组  {reassembly_text}")

        # MQTT 连接状态
        if self.mqtt_output is not None and self.mqtt_output.connected:
            self.mqtt_metric.setText("MQTT  已连接")
        elif self.mqtt_output is not None:
            self.mqtt_metric.setText("MQTT  未连接")
        else:
            self.mqtt_metric.setText("MQTT  已禁用")

        # 告警指示器
        alert_level = 0
        if current_point is not None and (current_point.status & STATUS_ALERT_MASK):
            alert_level = current_point.status & STATUS_ALERT_MASK

        if alert_level > 0:
            self.alarm_metric.setText(f"告警  Lv{alert_level}")
            self.alarm_metric.setObjectName("alarmActive")
        else:
            self.alarm_metric.setText("告警  正常")
            self.alarm_metric.setObjectName("alarmClear")
        self.alarm_metric.style().unpolish(self.alarm_metric)
        self.alarm_metric.style().polish(self.alarm_metric)

        # ── 当前点信息 ─────────────────────────────────────────
        if current_point is None:
            self.current_point_label.setText("当前点: 等待数据...")
        else:
            status_desc = f"0x{current_point.status:02X}"
            self.current_point_label.setText(
                "当前点: "
                f"{current_point.distance_cm} cm  |  {current_point.angle_deg:.2f} deg  |  "
                f"X {current_point.x_mm / 1000.0:.2f} m  |  Y {current_point.y_mm / 1000.0:.2f} m  |  "
                f"Q {current_point.quality}  |  状态 {status_desc}"
            )

        # ── 数据源信息 ─────────────────────────────────────────
        if self.mode == "live":
            source_text = f"数据源: 实时 CAN / {self.channel}"
            if self.csv_writer is not None:
                source_path = f"录制路径: {self.csv_writer.csv_path}"
            else:
                source_path = "录制路径: 未配置"
            detail_text = reassembly_text
        elif self.replay_source is None:
            source_text = "数据源: 回放模式 / 未加载 CSV"
            source_path = "CSV 路径: 请从右侧选择文件"
            detail_text = "回放控制: 暂无数据"
        else:
            source_text = f"数据源: CSV 回放 / 共 {len(self.replay_source.points)} 点"
            source_path = f"CSV 路径: {self.replay_source.csv_path}"
            detail_text = reassembly_text

        self.source_label.setText(f"{source_text}\n{source_path}")
        self.source_path_label.setText(source_path)

        # ── 重组统计快照 ────────────────────────────────────
        if self.mode == "live" and self.assembler is not None:
            reassembly = self.assembler.stats_snapshot()
        elif self.replay_source is not None:
            reassembly = self.replay_source.stats_snapshot()
        else:
            reassembly = {"ok": 0, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 0}

        # ── 回放进度 ─────────────────────────────────────────
        replay_pct = None
        if self.mode == "replay" and self.replay_source is not None and self.replay_source.duration_us > 0:
            replay_pct = self.replay_current_us / self.replay_source.duration_us * 100

        # ── core 设备状态汇总 (纯计算) ───────────────────────
        device_summary = compute_device_summary(
            mode=self.mode,
            visible_points=visible_points,
            sweep_points=self._last_sweep_points,
            current_point=current_point,
            reassembly=reassembly,
            replay_progress_pct=replay_pct,
        )

        # ── 扇区摘要面板 ─────────────────────────────────────
        sector_lines = []
        for sec in device_summary["sectors"]:
            d = sec.get("min_distance_cm")
            dist_str = f"{d}cm" if d is not None else "—"
            alert_str = f"Lv{sec['alert_level']}" if sec.get("alert_level", 0) > 0 else "OK"
            sector_lines.append(
                f"{sec['name']:6s}  pts={sec.get('point_count', 0):4d}  "
                f"min={dist_str:>6s}  {alert_str}"
            )
        self.sector_panel_label.setText("\n".join(sector_lines) if sector_lines else "暂无扇区数据")

        # ── 控制面板状态区 (分段展示) ──────────────────────────
        min_dist_str = "—"
        if device_summary["min_distance_cm"] is not None:
            min_dist_str = (
                f"{device_summary['min_distance_cm']} cm "
                f"@ {device_summary['min_distance_angle_deg']}°"
            )

        mqtt_status_str = (
            f"{self.mqtt_output.host}:{self.mqtt_output.port} (已连接)"
            if self.mqtt_output is not None and self.mqtt_output.connected
            else "已禁用" if self.mqtt_output is None
            else "未连接"
        )

        alert_lv = device_summary["alert_level"]
        status_lines = [
            f"模式: {'实时接收' if self.mode == 'live' else 'CSV 回放'}",
            f"可视点数: {device_summary['point_count']}",
            f"扫描点数: {device_summary['sweep_point_count']}",
            f"当前量程: {self.range_combo.currentText()}",
            f"最近距离: {min_dist_str}",
            f"告警等级: Lv{alert_lv}{' (活跃)' if device_summary['is_alert'] else ' (正常)'}",
            f"MQTT: {mqtt_status_str}",
        ]
        if replay_pct is not None:
            status_lines.append(f"回放进度: {replay_pct:.1f}%")
        status_lines.append("")
        status_lines.append(f"重组统计:")
        status_lines.append(f"  {reassembly_text}")
        self.status_panel_label.setText("\n".join(status_lines))

        # ── 日志输出 (2s 节流) ──────────────────────────────
        now_s = time.monotonic()
        if now_s - self._log_output_last_s >= 2.0:
            self._log_output_last_s = now_s
            self._log_output.emit_summary(device_summary)

        # ── MQTT telemetry 发布 (03 §5.3.2) ───────────────────────
        # alarm 检测已移至 ingest_live_point / advance_replay (03 §8.2)
        if self.mqtt_output is not None and self.mqtt_output.connected:
            now_s = time.monotonic()

            # telemetry: 使用配置的节流间隔 (03 §6.6)
            throttle_s = self.mqtt_output.telemetry_interval_s
            if now_s - self._mqtt_last_telemetry_s >= throttle_s:
                self._mqtt_last_telemetry_s = now_s

                telemetry = build_telemetry_dict(
                    device_id=self.mqtt_output.device_id,
                    mode=self.mode,
                    visible_points=visible_points,
                    sweep_points=self._last_sweep_points,
                    current_point=current_point,
                    reassembly=reassembly,
                    replay_progress_pct=replay_pct,
                )

                self.mqtt_output.publish_telemetry(telemetry)

    def shutdown(self):
        if self.closed:
            return

        self.closed = True
        self.poll_timer.stop()
        self.replay_timer.stop()
        self.render_timer.stop()

        if self.mode == "live" and self.assembler is not None:
            self.assembler.prune_stale_frames()
            if self.csv_writer is not None:
                self.csv_writer.write_summary(self.assembler.stats_snapshot())

        if self.csv_writer is not None:
            try:
                self.csv_writer.close()
            except OSError:
                pass

        if self.bus is not None:
            try:
                self.bus.shutdown()
            except OSError:
                pass

        if self._log_output is not None:
            try:
                self._log_output.close()
            except Exception:
                pass

        if self.mqtt_output is not None:
            try:
                self.mqtt_output.disconnect()
            except Exception:
                pass

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="2D LiDAR 点云实时接收与回放工具")
    parser.add_argument("--mode", choices=("live", "replay"), default="live")
    parser.add_argument("--channel", default="can0")
    parser.add_argument(
        "--can-interface",
        default=None,
        help="python-can interface. Linux live 默认 socketcan；Windows live 需显式指定 virtual/pcan/kvaser/vector/slcan 等。",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        default=None,
        help="CAN bitrate，部分 Windows backend 或 slcan 需要，例如 500000。",
    )
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--save-csv", type=Path)
    parser.add_argument("--replay-speed", choices=("0.5", "1", "2"), default="1")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT broker 地址")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker 端口")
    parser.add_argument("--no-mqtt", action="store_true", help="禁用 MQTT 输出")
    return parser.parse_args(argv)


def main(argv=None):
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    args = parse_args(argv)
    app = QtWidgets.QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName("2D LiDAR 点云台")
    pg.setConfigOptions(antialias=True)

    # ── MQTT 输出 (03 §8.1) ──────────────────────────────────────
    mqtt_output = None
    if not args.no_mqtt:
        mqtt_output = MqttOutput(
            host=args.mqtt_host,
            port=args.mqtt_port,
        )
        mqtt_output.set_mode(args.mode)
        mqtt_output.connect()  # connect_async: 不阻塞 UI 启动
        print(f"[MQTT] 异步连接 {args.mqtt_host}:{args.mqtt_port} ...", flush=True)

    window = None
    csv_writer = None
    try:
        if args.mode == "live":
            bus = open_bus(
                args.channel,
                interface=args.can_interface,
                bitrate=args.bitrate,
            )
            save_csv = args.save_csv.resolve() if args.save_csv else build_default_csv_path()
            csv_writer = CsvPointWriter(save_csv)
            window = PointCloudWindow(
                mode="live",
                channel=args.channel,
                replay_speed=float(args.replay_speed),
                bus=bus,
                csv_writer=csv_writer,
                mqtt_output=mqtt_output,
            )
            print(f"开始实时接收 CAN 数据，通道: {args.channel}", flush=True)
            print(f"正式 CSV 输出: {csv_writer.csv_path}", flush=True)
            print(f"重组摘要输出: {csv_writer.summary_path}", flush=True)
        else:
            window = PointCloudWindow(
                mode="replay",
                channel=args.channel,
                replay_speed=float(args.replay_speed),
                replay_csv_path=args.input_csv.resolve() if args.input_csv else None,
                mqtt_output=mqtt_output,
            )
            if args.input_csv:
                print(f"加载回放 CSV: {args.input_csv.resolve()}", flush=True)
            else:
                print("回放模式启动完成，请从右侧选择 CSV。", flush=True)

        # ── MQTT 命令白名单 ────────────────────────────────────
        if mqtt_output is not None:
            dispatcher = CmdDispatcher()

            def handle_ping(topic, payload):
                req_id = payload.get("req_id", "")
                print(f"MQTT cmd: cmd=ping req_id={req_id} result=OK", flush=True)

            def handle_pause_replay(topic, payload):
                req_id = payload.get("req_id", "")
                if window.mode != "replay":
                    print(f"MQTT cmd: cmd=pause_replay req_id={req_id} result=REJECTED wrong_mode(current={window.mode})", flush=True)
                    return
                if not window.replay_playing:
                    print(f"MQTT cmd: cmd=pause_replay req_id={req_id} result=OK (already paused)", flush=True)
                    return
                window.toggle_playback()
                print(f"MQTT cmd: cmd=pause_replay req_id={req_id} result=OK", flush=True)

            def handle_resume_replay(topic, payload):
                req_id = payload.get("req_id", "")
                if window.mode != "replay":
                    print(f"MQTT cmd: cmd=resume_replay req_id={req_id} result=REJECTED wrong_mode(current={window.mode})", flush=True)
                    return
                if window.replay_playing:
                    print(f"MQTT cmd: cmd=resume_replay req_id={req_id} result=OK (already playing)", flush=True)
                    return
                window.toggle_playback()
                print(f"MQTT cmd: cmd=resume_replay req_id={req_id} result=OK", flush=True)

            def handle_set_replay_speed(topic, payload):
                req_id = payload.get("req_id", "")
                raw = payload.get("speed")
                if raw is None:
                    print(f"MQTT cmd: cmd=set_replay_speed req_id={req_id} result=REJECTED missing_speed", flush=True)
                    return
                try:
                    speed = float(raw)
                except (TypeError, ValueError):
                    print(f"MQTT cmd: cmd=set_replay_speed req_id={req_id} result=REJECTED invalid_speed({raw!r})", flush=True)
                    return
                if window.mode != "replay":
                    print(f"MQTT cmd: cmd=set_replay_speed req_id={req_id} result=REJECTED wrong_mode(current={window.mode})", flush=True)
                    return
                ALLOWED_SPEEDS = {0.5, 1.0, 2.0}
                if speed not in ALLOWED_SPEEDS:
                    print(f"MQTT cmd: cmd=set_replay_speed req_id={req_id} result=REJECTED invalid_speed({speed})", flush=True)
                    return
                window.change_replay_speed(f"{speed:g}x")
                print(f"MQTT cmd: cmd=set_replay_speed req_id={req_id} result=OK speed={speed:g}", flush=True)

            dispatcher.register("ping", handle_ping)
            dispatcher.register("pause_replay", handle_pause_replay)
            dispatcher.register("resume_replay", handle_resume_replay)
            dispatcher.register("set_replay_speed", handle_set_replay_speed)

            mqtt_output.subscribe_cmd(dispatcher.dispatch)
            print("[MQTT] 命令白名单已注册: ping, pause_replay, resume_replay, set_replay_speed", flush=True)

        window.show()
        return app.exec()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
            QtWidgets.QMessageBox.critical(None, "启动失败", str(exc))
        return 1
    finally:
        if window is None and csv_writer is not None:
            csv_writer.close()
        if window is not None:
            window.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
