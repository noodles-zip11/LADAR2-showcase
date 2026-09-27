#!/usr/bin/env python3
"""M8 offline CSV analysis.

The analyzer is intentionally offline-only: it reads CSV files and optional
label files, then prints or writes a Markdown report. It does not open CAN
hardware and does not depend on the live receiver.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {"host_rx_time_us", "angle_deg", "distance_cm"}
OPTIONAL_FIELDS = {"t_sample_us", "angle_tick", "x_mm", "y_mm", "quality", "status"}

STATUS_ALERT_MASK = 0x07
STATUS_ESTIMATED_FLAG = 0x08
DEFAULT_ANGLE_BIN_DEG = 10.0


def parse_float(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "")
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def load_points(path: Path) -> tuple[list[dict[str, float | int | None]], list[str]]:
    points: list[dict[str, float | int | None]] = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        missing = REQUIRED_FIELDS - set(fieldnames)
        if missing:
            raise ValueError(f"{path} missing required fields: {sorted(missing)}")

        for row_index, row in enumerate(reader, start=2):
            host_rx_time_us = parse_float(row, "host_rx_time_us")
            angle_deg = parse_float(row, "angle_deg")
            distance_cm = parse_float(row, "distance_cm")
            if host_rx_time_us is None or angle_deg is None or distance_cm is None:
                points.append({"row": row_index, "valid": 0})
                continue

            point: dict[str, float | int | None] = {
                "row": row_index,
                "valid": 1,
                "host_rx_time_us": host_rx_time_us,
                "angle_deg": angle_deg % 360.0,
                "distance_cm": distance_cm,
            }
            for field in OPTIONAL_FIELDS:
                point[field] = parse_float(row, field)
            points.append(point)
    return points, fieldnames


def load_labels(path: Path | None) -> Counter[str]:
    if path is None or not path.exists():
        return Counter()
    counts: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"start_host_rx_time_us", "end_host_rx_time_us", "label"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} missing label fields: {sorted(missing)}")
        for row in reader:
            label = (row.get("label") or "").strip()
            if label:
                counts[label] += 1
    return counts


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percent / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def estimate_rate_hz(times_us: list[float]) -> float | None:
    if len(times_us) < 2:
        return None
    span_s = (max(times_us) - min(times_us)) / 1_000_000.0
    if span_s <= 0.0:
        return None
    return (len(times_us) - 1) / span_s


def compact_distribution(values: list[int]) -> dict[int, int]:
    return dict(sorted(Counter(values).items()))


def angle_coverage(points: list[dict[str, float | int | None]], bin_deg: float) -> tuple[Counter[int], float]:
    bins: Counter[int] = Counter()
    if bin_deg <= 0.0:
        raise ValueError("bin_deg must be positive")
    possible_bins = int(math.ceil(360.0 / bin_deg))
    for point in points:
        angle = float(point["angle_deg"])
        bin_id = int(angle // bin_deg)
        bins[bin_id] += 1
    coverage_ratio = len(bins) / possible_bins if possible_bins else 0.0
    return bins, coverage_ratio


def outline_stability(points: list[dict[str, float | int | None]], bin_deg: float) -> dict[str, Any]:
    per_bin_distances: dict[int, list[float]] = {}
    for point in points:
        bin_id = int(float(point["angle_deg"]) // bin_deg)
        per_bin_distances.setdefault(bin_id, []).append(float(point["distance_cm"]))

    spreads = []
    usable_bins = 0
    for distances in per_bin_distances.values():
        if len(distances) < 3:
            continue
        p95 = percentile(distances, 95)
        p05 = percentile(distances, 5)
        if p95 is None or p05 is None:
            continue
        usable_bins += 1
        spreads.append(p95 - p05)

    return {
        "outline_usable_bins": usable_bins,
        "outline_spread_cm_median": statistics.median(spreads) if spreads else None,
        "outline_spread_cm_p95": percentile(spreads, 95),
    }


def compute_metrics(
    points: list[dict[str, float | int | None]],
    *,
    angle_bin_deg: float = DEFAULT_ANGLE_BIN_DEG,
    low_quality_threshold: float = 10.0,
    near_obstacle_cm: float = 50.0,
    too_near_cm: float = 30.0,
) -> dict[str, Any]:
    valid_points = [p for p in points if p.get("valid") == 1]
    times = [float(p["host_rx_time_us"]) for p in valid_points]
    distances = [float(p["distance_cm"]) for p in valid_points]
    qualities = [float(p["quality"]) for p in valid_points if p.get("quality") is not None]
    statuses = [int(float(p["status"])) for p in valid_points if p.get("status") is not None]
    alert_levels = [status & STATUS_ALERT_MASK for status in statuses]

    invalid_count = len(points) - len(valid_points)
    nonpositive_distance_count = sum(1 for value in distances if value <= 0.0)
    low_quality_count = sum(1 for value in qualities if value < low_quality_threshold)
    status_alert_count = sum(1 for level in alert_levels if level != 0)
    estimated_count = sum(1 for status in statuses if status & STATUS_ESTIMATED_FLAG)
    near_obstacle_count = sum(1 for value in distances if 0.0 < value <= near_obstacle_cm)
    too_near_count = sum(1 for value in distances if 0.0 < value <= too_near_cm)

    anomaly_candidate_count = (
        invalid_count
        + nonpositive_distance_count
        + low_quality_count
        + status_alert_count
    )
    anomaly_candidate_ratio = anomaly_candidate_count / len(points) if points else 0.0

    angle_bins, angle_coverage_ratio = angle_coverage(valid_points, angle_bin_deg)
    stability = outline_stability(valid_points, angle_bin_deg)

    metrics: dict[str, Any] = {
        "total_rows": len(points),
        "valid_points": len(valid_points),
        "invalid_rows": invalid_count,
        "duration_s": ((max(times) - min(times)) / 1_000_000.0) if len(times) >= 2 else None,
        "estimated_rate_hz": estimate_rate_hz(times),
        "distance_cm_min": min(distances) if distances else None,
        "distance_cm_median": statistics.median(distances) if distances else None,
        "distance_cm_p95": percentile(distances, 95),
        "distance_cm_max": max(distances) if distances else None,
        "quality_median": statistics.median(qualities) if qualities else None,
        "quality_min": min(qualities) if qualities else None,
        "low_quality_count": low_quality_count,
        "status_distribution": compact_distribution(statuses),
        "status_alert_distribution": compact_distribution(alert_levels),
        "status_alert_count": status_alert_count,
        "estimated_flag_count": estimated_count,
        "estimated_flag_ratio": estimated_count / len(statuses) if statuses else None,
        "near_obstacle_count": near_obstacle_count,
        "too_near_count": too_near_count,
        "anomaly_candidate_count": anomaly_candidate_count,
        "anomaly_candidate_ratio": anomaly_candidate_ratio,
        "angle_bin_deg": angle_bin_deg,
        "angle_bin_count": len(angle_bins),
        "angle_coverage_ratio": angle_coverage_ratio,
        "angle_bin_min_points": min(angle_bins.values()) if angle_bins else None,
        "angle_bin_max_points": max(angle_bins.values()) if angle_bins else None,
    }
    metrics.update(stability)
    return metrics


def format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_markdown(input_path: Path, fieldnames: list[str], metrics: dict[str, Any], labels: Counter[str]) -> str:
    lines = [
        "# M8 离线分析报告",
        "",
        f"- 输入文件：`{input_path}`",
        f"- 字段：`{', '.join(fieldnames)}`",
        "",
        "## 基础指标",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
    ]
    for key, value in metrics.items():
        lines.append(f"| `{key}` | {format_value(value)} |")

    lines.extend(["", "## 标签分布", "", "| 标签 | 片段数 |", "| --- | --- |"])
    if labels:
        for label, count in sorted(labels.items()):
            lines.append(f"| `{label}` | {count} |")
    else:
        lines.append("| n/a | 0 |")

    lines.extend([
        "",
        "## 口径说明",
        "",
        "- `status & 0x07` 表示告警等级；仅该低 3 位非零时计入 `status_alert_count`。",
        "- `status=0x08` 是 estimated 标记，不单独视为异常。",
        "- `anomaly_candidate_ratio` 是离线筛查指标，不等同于人工场景标签或最终算法判定。",
        "- `outline_spread_cm_*` 是按角度分箱统计的距离离散程度，只用于粗看轮廓稳定性。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze an M8 CSV dataset.")
    parser.add_argument("--input", required=True, type=Path, help="Input CSV path.")
    parser.add_argument("--labels", type=Path, help="Optional labels CSV path.")
    parser.add_argument("--output", type=Path, help="Optional Markdown report path.")
    parser.add_argument("--angle-bin-deg", type=float, default=DEFAULT_ANGLE_BIN_DEG)
    args = parser.parse_args()

    points, fieldnames = load_points(args.input)
    labels = load_labels(args.labels)
    metrics = compute_metrics(points, angle_bin_deg=args.angle_bin_deg)
    report = render_markdown(args.input, fieldnames, metrics, labels)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
