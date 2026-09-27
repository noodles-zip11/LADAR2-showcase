#!/usr/bin/env python3
"""Scan M6 offline tuning parameters and write a recommendation.

This tool only changes offline analysis outputs. It does not modify raw CSV
files, MCU firmware, or the CAN protocol.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from m6_geometry_quality import (
    RepeatData,
    angle_mask,
    compute_gap_counts,
    compute_repeatability,
    compute_seam_gaps,
    fit_line_pca,
    fmt,
    select_box_edges,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual"


@dataclass
class Candidate:
    angle_offset_deg: float
    box_min_distance_mm: float
    box_max_distance_mm: float
    gap_threshold_mm: float
    box_repeatability_p95_mm: float
    box_seam_gap_mm: float
    box_edge_rmse_mm: float
    box_gap_count: int
    wall_line_rmse_mm: float
    wall_residual_p95_mm: float
    wall_repeat_offset_mm: float
    wall_gap_count: int
    score: float


def parse_range(text: str) -> list[float]:
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(float(part))
    return values


def frange(start: float, stop: float, step: float) -> list[float]:
    values = []
    current = start
    while current <= stop + (step / 2.0):
        values.append(round(current, 6))
        current += step
    return values


def corrected_xy(distance_mm: float, angle_deg: float, angle_offset_deg: float) -> tuple[float, float]:
    theta = math.radians((angle_deg + angle_offset_deg) % 360.0)
    return distance_mm * math.cos(theta), distance_mm * math.sin(theta)


def load_corrected_repeat(
    path: Path,
    *,
    min_distance_mm: float,
    max_distance_mm: float,
    angle_offset_deg: float,
) -> RepeatData:
    xs = []
    ys = []
    corrected_angles = []
    distances = []
    times = []
    raw_count = 0

    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            raw_count += 1
            try:
                raw_angle = float(row["angle_deg"]) % 360.0
                distance_mm = float(row["distance_cm"]) * 10.0
                host_rx_time_us = float(row["host_rx_time_us"])
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in (raw_angle, distance_mm, host_rx_time_us)):
                continue
            if distance_mm < min_distance_mm or distance_mm > max_distance_mm:
                continue

            x, y = corrected_xy(distance_mm, raw_angle, angle_offset_deg)
            xs.append(x)
            ys.append(y)
            corrected_angles.append((raw_angle + angle_offset_deg) % 360.0)
            distances.append(distance_mm)
            times.append(host_rx_time_us)

    return RepeatData(
        name=path.stem,
        path=path,
        raw_count=raw_count,
        x=np.asarray(xs, dtype=float),
        y=np.asarray(ys, dtype=float),
        angle_deg=np.asarray(corrected_angles, dtype=float),
        distance_mm=np.asarray(distances, dtype=float),
        host_rx_time_us=np.asarray(times, dtype=float),
    )


def load_box_repeats(
    data_dir: Path,
    *,
    angle_offset_deg: float,
    box_min_distance_mm: float,
    box_max_distance_mm: float,
) -> list[RepeatData]:
    repeats = []
    for name in ("repeat_far_01.csv", "repeat_far_02.csv", "repeat_far_03.csv"):
        repeats.append(
            load_corrected_repeat(
                data_dir / name,
                min_distance_mm=box_min_distance_mm,
                max_distance_mm=box_max_distance_mm,
                angle_offset_deg=angle_offset_deg,
            )
        )
    return repeats


def selected_wall_points(
    path: Path,
    *,
    angle_offset_deg: float,
    wall_start_deg: float,
    wall_end_deg: float,
    wall_min_distance_mm: float,
    wall_max_distance_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    points = []
    times = []
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                raw_angle = float(row["angle_deg"]) % 360.0
                distance_mm = float(row["distance_cm"]) * 10.0
                host_rx_time_us = float(row["host_rx_time_us"])
            except (TypeError, ValueError):
                continue
            if not angle_mask(np.asarray([raw_angle]), wall_start_deg, wall_end_deg)[0]:
                continue
            if distance_mm < wall_min_distance_mm or distance_mm > wall_max_distance_mm:
                continue
            x, y = corrected_xy(distance_mm, raw_angle, angle_offset_deg)
            points.append((x, y))
            times.append(host_rx_time_us)
    return np.asarray(points, dtype=float), np.asarray(times, dtype=float)


def wall_metrics(
    data_dir: Path,
    *,
    angle_offset_deg: float,
    gap_threshold_mm: float,
    wall_start_deg: float,
    wall_end_deg: float,
    wall_min_distance_mm: float,
    wall_max_distance_mm: float,
) -> dict:
    all_points = []
    centers = []
    total_gap_count = 0
    for name in ("wall_01.csv", "wall_02.csv", "wall_03.csv"):
        points, times = selected_wall_points(
            data_dir / name,
            angle_offset_deg=angle_offset_deg,
            wall_start_deg=wall_start_deg,
            wall_end_deg=wall_end_deg,
            wall_min_distance_mm=wall_min_distance_mm,
            wall_max_distance_mm=wall_max_distance_mm,
        )
        if len(points) == 0:
            continue
        fit = fit_line_pca(points)
        centers.append(fit["center"])
        all_points.append(points)

        order = np.argsort(times)
        ordered = points[order]
        if len(ordered) >= 2:
            gaps = np.hypot(np.diff(ordered[:, 0]), np.diff(ordered[:, 1]))
            total_gap_count += int(np.count_nonzero(gaps > gap_threshold_mm))

    if not all_points:
        return {
            "line_rmse_mm": float("nan"),
            "residual_p95_mm": float("nan"),
            "repeat_offset_mm": float("nan"),
            "gap_count": 0,
        }

    combined = np.vstack(all_points)
    fit = fit_line_pca(combined)
    center_stack = np.vstack(centers)
    median_center = np.median(center_stack, axis=0)
    repeat_offsets = np.hypot(center_stack[:, 0] - median_center[0], center_stack[:, 1] - median_center[1])

    return {
        "line_rmse_mm": fit["rmse"],
        "residual_p95_mm": fit["p95"],
        "repeat_offset_mm": float(np.max(repeat_offsets)),
        "gap_count": total_gap_count,
    }


def evaluate_candidate(
    data_dir: Path,
    *,
    angle_offset_deg: float,
    box_min_distance_mm: float,
    box_max_distance_mm: float,
    gap_threshold_mm: float,
    wall_start_deg: float,
    wall_end_deg: float,
    wall_min_distance_mm: float,
    wall_max_distance_mm: float,
) -> Candidate:
    box_repeats = load_box_repeats(
        data_dir,
        angle_offset_deg=angle_offset_deg,
        box_min_distance_mm=box_min_distance_mm,
        box_max_distance_mm=box_max_distance_mm,
    )
    if any(len(repeat.x) < 100 for repeat in box_repeats):
        raise ValueError("too few box points after filtering")

    repeatability = compute_repeatability(box_repeats, bin_width_deg=1.0, min_bin_points=3)
    seam = compute_seam_gaps(box_repeats, seam_window_deg=2.0)
    gaps = compute_gap_counts(box_repeats, gap_threshold_mm=gap_threshold_mm)
    edge_fit = select_box_edges(
        box_repeats,
        edge_percentile=5.0,
        edge_band_mm=35.0,
        min_points=120,
    )
    wall = wall_metrics(
        data_dir,
        angle_offset_deg=angle_offset_deg,
        gap_threshold_mm=gap_threshold_mm,
        wall_start_deg=wall_start_deg,
        wall_end_deg=wall_end_deg,
        wall_min_distance_mm=wall_min_distance_mm,
        wall_max_distance_mm=wall_max_distance_mm,
    )

    box_edge_rmse = float(edge_fit["line_rmse_mm"])
    repeat_p95 = float(repeatability["repeatability_p95_mm"])
    seam_gap = float(seam["seam_gap_mm"])
    wall_rmse = float(wall["line_rmse_mm"])
    wall_offset = float(wall["repeat_offset_mm"])
    box_gap_count = int(gaps["point_drop_or_gap_count"])
    wall_gap_count = int(wall["gap_count"])

    # Score favors better box geometry while preserving the already-good wall result.
    score_inputs = (box_edge_rmse, repeat_p95, seam_gap, wall_rmse, wall_offset)
    if all(math.isfinite(value) for value in score_inputs):
        score = (
            box_edge_rmse
            + 0.25 * repeat_p95
            + 0.10 * seam_gap
            + 0.10 * box_gap_count
            + 0.50 * max(0.0, wall_rmse - 8.0)
            + 0.25 * max(0.0, wall_offset - 8.0)
            + 0.05 * wall_gap_count
        )
    else:
        score = float("inf")

    return Candidate(
        angle_offset_deg=angle_offset_deg,
        box_min_distance_mm=box_min_distance_mm,
        box_max_distance_mm=box_max_distance_mm,
        gap_threshold_mm=gap_threshold_mm,
        box_repeatability_p95_mm=repeat_p95,
        box_seam_gap_mm=seam_gap,
        box_edge_rmse_mm=box_edge_rmse,
        box_gap_count=box_gap_count,
        wall_line_rmse_mm=wall_rmse,
        wall_residual_p95_mm=float(wall["residual_p95_mm"]),
        wall_repeat_offset_mm=wall_offset,
        wall_gap_count=wall_gap_count,
        score=float(score),
    )


def write_csv(path: Path, candidates: list[Candidate]):
    fields = [
        "score",
        "angle_offset_deg",
        "box_min_distance_mm",
        "box_max_distance_mm",
        "gap_threshold_mm",
        "box_repeatability_p95_mm",
        "box_seam_gap_mm",
        "box_edge_rmse_mm",
        "box_gap_count",
        "wall_line_rmse_mm",
        "wall_residual_p95_mm",
        "wall_repeat_offset_mm",
        "wall_gap_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for item in candidates:
            writer.writerow({field: getattr(item, field) for field in fields})


def write_recommendation(path: Path, baseline: Candidate, best: Candidate, candidates: list[Candidate]):
    lines = [
        "# M6 Tuning Scan",
        "",
        "This scan changes only offline analysis parameters. Raw CSV files and MCU firmware are unchanged.",
        "",
        "## Baseline",
        "",
        "| parameter / metric | value |",
        "| --- | ---: |",
        f"| angle_offset_deg | {fmt(baseline.angle_offset_deg)} |",
        f"| box_min_distance_mm | {fmt(baseline.box_min_distance_mm)} |",
        f"| box_max_distance_mm | {fmt(baseline.box_max_distance_mm)} |",
        f"| gap_threshold_mm | {fmt(baseline.gap_threshold_mm)} |",
        f"| box_edge_rmse_mm | {fmt(baseline.box_edge_rmse_mm)} |",
        f"| box_repeatability_p95_mm | {fmt(baseline.box_repeatability_p95_mm)} |",
        f"| box_gap_count | {baseline.box_gap_count} |",
        f"| wall_line_rmse_mm | {fmt(baseline.wall_line_rmse_mm)} |",
        f"| wall_repeat_offset_mm | {fmt(baseline.wall_repeat_offset_mm)} |",
        "",
        "## Recommended Offline Configuration",
        "",
        "| parameter / metric | value |",
        "| --- | ---: |",
        f"| angle_offset_deg | {fmt(best.angle_offset_deg)} |",
        f"| box_min_distance_mm | {fmt(best.box_min_distance_mm)} |",
        f"| box_max_distance_mm | {fmt(best.box_max_distance_mm)} |",
        f"| gap_threshold_mm | {fmt(best.gap_threshold_mm)} |",
        f"| box_edge_rmse_mm | {fmt(best.box_edge_rmse_mm)} |",
        f"| box_repeatability_p95_mm | {fmt(best.box_repeatability_p95_mm)} |",
        f"| box_gap_count | {best.box_gap_count} |",
        f"| wall_line_rmse_mm | {fmt(best.wall_line_rmse_mm)} |",
        f"| wall_repeat_offset_mm | {fmt(best.wall_repeat_offset_mm)} |",
        f"| score | {fmt(best.score)} |",
        "",
        "## Top 10 Candidates",
        "",
        "| rank | score | offset_deg | box_min_mm | box_max_mm | gap_mm | box_edge_rmse | wall_rmse | box_gap | wall_gap |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, item in enumerate(candidates[:10], start=1):
        lines.append(
            f"| {rank} | {fmt(item.score)} | {fmt(item.angle_offset_deg)} | "
            f"{fmt(item.box_min_distance_mm)} | {fmt(item.box_max_distance_mm)} | "
            f"{fmt(item.gap_threshold_mm)} | {fmt(item.box_edge_rmse_mm)} | "
            f"{fmt(item.wall_line_rmse_mm)} | {item.box_gap_count} | {item.wall_gap_count} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- A constant angle offset mostly rotates the XY frame; it should not be expected to fix curvature by itself.",
        "- If the recommended score improves mainly through distance filtering, keep this as an analysis/display policy rather than changing MCU data.",
        "- If future wall RMSE becomes high under the same scan, then re-open synchronization or mounting diagnostics.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--angle-offset-start", type=float, default=-3.0)
    parser.add_argument("--angle-offset-stop", type=float, default=3.0)
    parser.add_argument("--angle-offset-step", type=float, default=1.0)
    parser.add_argument("--box-min-distance-mm", default="280,300,320")
    parser.add_argument("--box-max-distance-mm", default="1000")
    parser.add_argument("--gap-threshold-mm", default="80,120")
    parser.add_argument("--wall-start-deg", type=float, default=350.0)
    parser.add_argument("--wall-end-deg", type=float, default=40.0)
    parser.add_argument("--wall-min-distance-mm", type=float, default=350.0)
    parser.add_argument("--wall-max-distance-mm", type=float, default=1000.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_dir = args.run_dir.resolve()
    data_dir = run_dir / "data"
    output_csv = run_dir / "tuning_scan.csv"
    output_md = run_dir / "tuning_scan.md"

    offsets = frange(args.angle_offset_start, args.angle_offset_stop, args.angle_offset_step)
    box_min_values = parse_range(args.box_min_distance_mm)
    box_max_values = parse_range(args.box_max_distance_mm)
    gap_values = parse_range(args.gap_threshold_mm)

    candidates = []
    for offset in offsets:
        for box_min in box_min_values:
            for box_max in box_max_values:
                if box_min >= box_max:
                    continue
                for gap_threshold in gap_values:
                    try:
                        candidates.append(
                            evaluate_candidate(
                                data_dir,
                                angle_offset_deg=offset,
                                box_min_distance_mm=box_min,
                                box_max_distance_mm=box_max,
                                gap_threshold_mm=gap_threshold,
                                wall_start_deg=args.wall_start_deg,
                                wall_end_deg=args.wall_end_deg,
                                wall_min_distance_mm=args.wall_min_distance_mm,
                                wall_max_distance_mm=args.wall_max_distance_mm,
                            )
                        )
                    except Exception:
                        continue

    if not candidates:
        raise SystemExit("no tuning candidates could be evaluated")

    candidates.sort(key=lambda item: (not math.isfinite(item.score), item.score))
    baseline = evaluate_candidate(
        data_dir,
        angle_offset_deg=0.0,
        box_min_distance_mm=280.0,
        box_max_distance_mm=1000.0,
        gap_threshold_mm=120.0,
        wall_start_deg=args.wall_start_deg,
        wall_end_deg=args.wall_end_deg,
        wall_min_distance_mm=args.wall_min_distance_mm,
        wall_max_distance_mm=args.wall_max_distance_mm,
    )
    best = candidates[0]

    write_csv(output_csv, candidates)
    write_recommendation(output_md, baseline, best, candidates)
    print(f"scan_csv={output_csv}")
    print(f"recommendation={output_md}")
    print(
        "best="
        f"offset={best.angle_offset_deg:g},"
        f"box_min={best.box_min_distance_mm:g},"
        f"box_max={best.box_max_distance_mm:g},"
        f"gap={best.gap_threshold_mm:g},"
        f"box_rmse={best.box_edge_rmse_mm:.2f},"
        f"wall_rmse={best.wall_line_rmse_mm:.2f},"
        f"score={best.score:.2f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
