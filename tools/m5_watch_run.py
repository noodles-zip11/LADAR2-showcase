#!/usr/bin/env python3
"""Read-only live watcher for an M5 run directory.

This does not open the CAN adapter. It tails the CSV currently written by
tools/m5_long_run.py and shows a lightweight point-cloud/status UI.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from can_parser import LidarPoint


def latest_run_dir(root: Path) -> Path:
    runs = [path for path in root.iterdir() if path.is_dir() and path.name.startswith("m5_")]
    if not runs:
        raise RuntimeError(f"No M5 run directories found under {root}")
    return max(runs, key=lambda path: path.stat().st_mtime)


def find_point_csv(run_dir: Path) -> Path:
    data_dir = run_dir / "data"
    candidates = sorted(data_dir.glob("can_points_*.csv"))
    if not candidates:
        candidates = sorted(data_dir.glob("can_distance*.csv"))
    if not candidates:
        raise RuntimeError(f"No point CSV found under {data_dir}")
    return candidates[-1]


def parse_point(row: dict) -> LidarPoint:
    return LidarPoint(
        host_rx_time_us=int(row["host_rx_time_us"]),
        t_sample_us=int(row["t_sample_us"]),
        angle_tick=int(row["angle_tick"]),
        angle_deg=float(row["angle_deg"]),
        distance_cm=int(row["distance_cm"]),
        x_mm=float(row["x_mm"]),
        y_mm=float(row["y_mm"]),
        quality=int(row["quality"]),
        status=int(row["status"]),
    )


def load_tail_points(csv_path: Path, max_points: int) -> list[LidarPoint]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)
    except (OSError, csv.Error, ValueError):
        return []

    points = []
    for row in rows[-max_points:]:
        try:
            points.append(parse_point(row))
        except (KeyError, TypeError, ValueError):
            continue
    return points


class M5WatchWindow:
    def __init__(self, run_dir: Path, csv_path: Path, max_points: int, stale_s: float):
        from PySide6 import QtCore, QtWidgets
        import pyqtgraph as pg

        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.pg = pg
        self.run_dir = run_dir
        self.csv_path = csv_path
        self.max_points = max_points
        self.stale_s = stale_s
        self.last_count = 0
        self.last_growth_s = time.monotonic()
        self.start_s = time.monotonic()

        self.widget = QtWidgets.QWidget()
        self.widget.setWindowTitle(f"M5 watcher - {run_dir.name}")
        self.widget.resize(1180, 760)

        layout = QtWidgets.QVBoxLayout(self.widget)
        self.status = QtWidgets.QLabel()
        self.status.setStyleSheet("font-family: Consolas; font-size: 14px;")
        layout.addWidget(self.status)

        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "x", units="mm")
        self.plot.setLabel("left", "y", units="mm")
        self.scatter = self.plot.plot([], [], pen=None, symbol="o", symbolSize=4, symbolBrush=(40, 140, 255, 150))
        self.latest = self.plot.plot([], [], pen=None, symbol="o", symbolSize=10, symbolBrush=(255, 80, 80, 230))
        layout.addWidget(self.plot, stretch=1)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self):
        points = load_tail_points(self.csv_path, self.max_points)
        count = count_csv_rows(self.csv_path)
        now = time.monotonic()
        if count > self.last_count:
            self.last_growth_s = now
        self.last_count = count

        xs = [point.x_mm for point in points]
        ys = [point.y_mm for point in points]
        self.scatter.setData(xs, ys)
        if points:
            self.latest.setData([points[-1].x_mm], [points[-1].y_mm])
        else:
            self.latest.setData([], [])

        stale_for = now - self.last_growth_s
        state = "RUNNING" if stale_for <= self.stale_s else "STALE"
        latest_text = "NA"
        if points:
            latest_text = (
                f"{points[-1].distance_cm}cm @ {points[-1].angle_deg:.1f}deg "
                f"status=0x{points[-1].status:02X}"
            )
        self.status.setText(
            f"run={self.run_dir.name}  state={state}  rows={count}  "
            f"stale_for={stale_for:.1f}s  latest={latest_text}\n"
            f"csv={self.csv_path}"
        )


def count_csv_rows(csv_path: Path) -> int:
    try:
        with csv_path.open("r", encoding="utf-8") as csv_file:
            line_count = sum(1 for _ in csv_file)
    except OSError:
        return 0
    return max(0, line_count - 1)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Watch an active M5 run without opening CAN")
    parser.add_argument("--run-dir", type=Path, help="M5 run directory. Defaults to latest docs/m5/runs/m5_*")
    parser.add_argument("--max-points", type=int, default=3000)
    parser.add_argument("--stale-s", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_root = REPO_ROOT / "docs" / "m5" / "runs"
    run_dir = args.run_dir.resolve() if args.run_dir else latest_run_dir(run_root)
    csv_path = find_point_csv(run_dir)

    from PySide6 import QtWidgets

    app = QtWidgets.QApplication(sys.argv[:1])
    window = M5WatchWindow(run_dir, csv_path, args.max_points, args.stale_s)
    window.widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
