#!/usr/bin/env python3
"""Analyze the M6 box and wall repeat groups without touching firmware."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from m6_geometry_quality import (
    RepeatData,
    angle_mask,
    compute_gap_counts,
    compute_repeatability,
    compute_seam_gaps,
    fit_line_pca,
    fmt,
    load_repeat,
    select_box_edges,
    set_equal_axes,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual"


@dataclass
class WallSelection:
    start_deg: float
    end_deg: float
    min_distance_mm: float
    max_distance_mm: float
    points: np.ndarray
    sources: np.ndarray
    fit: dict
    per_run: list[dict]


def load_named_repeats(data_dir: Path, names: list[str], max_distance_cm: float) -> list[RepeatData]:
    repeats = []
    for name in names:
        path = data_dir / name
        if not path.exists():
            raise FileNotFoundError(path)
        repeats.append(load_repeat(path, max_distance_cm=max_distance_cm))
    return repeats


def save_scatter_overlay(repeats: list[RepeatData], out: Path, title: str):
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    for repeat, color in zip(repeats, colors):
        ax.scatter(repeat.x, repeat.y, s=3, alpha=0.35, label=f"{repeat.name} ({len(repeat.x)} pts)", c=color)
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=4)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def save_box_edge_fit(repeats: list[RepeatData], edge_fit: dict, out: Path):
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    repeat_colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    edge_colors = {
        "left": "#111111",
        "right": "#7f7f7f",
        "bottom": "#8c564b",
        "top": "#9467bd",
    }
    for edge_index, edge in enumerate(edge_fit["edges"]):
        points = edge["points"]
        sources = edge["sources"]
        for idx, repeat in enumerate(repeats):
            mask = sources == idx
            label = repeat.name if edge_index == 0 else None
            ax.scatter(points[mask, 0], points[mask, 1], s=4, alpha=0.25, label=label, c=repeat_colors[idx])

        fit = edge["fit"]
        center = fit["center"]
        direction = fit["direction"]
        projection = fit["projection"]
        t0 = float(np.min(projection))
        t1 = float(np.max(projection))
        line = np.vstack([center + direction * t0, center + direction * t1])
        ax.plot(line[:, 0], line[:, 1], c=edge_colors.get(edge["name"], "black"), linewidth=2, label=edge["name"])
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=3)
    ax.set_title("M6 box far edge fit")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def save_seam_closeup(repeats: list[RepeatData], out: Path, seam_window_deg: float):
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    xs = []
    ys = []
    for repeat, color in zip(repeats, colors):
        mask = (repeat.angle_deg <= seam_window_deg) | (repeat.angle_deg >= (360.0 - seam_window_deg))
        ax.scatter(repeat.x[mask], repeat.y[mask], s=8, alpha=0.55, label=repeat.name, c=color)
        xs.extend(repeat.x[mask].tolist())
        ys.extend(repeat.y[mask].tolist())
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=3)
    ax.set_title(f"M6 box far seam closeup: <= {seam_window_deg:g} or >= {360 - seam_window_deg:g} deg")
    if xs and ys:
        pad = 80.0
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def raw_wall_points(paths: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    points = []
    meta = []
    for source_idx, path in enumerate(paths):
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                try:
                    angle = float(row["angle_deg"]) % 360.0
                    distance_mm = float(row["distance_cm"]) * 10.0
                    x = float(row["x_mm"])
                    y = float(row["y_mm"])
                except (TypeError, ValueError):
                    continue
                if all(math.isfinite(v) for v in (angle, distance_mm, x, y)) and distance_mm > 0:
                    points.append((x, y))
                    meta.append((source_idx, angle, distance_mm))
    return np.asarray(points, dtype=float), np.asarray(meta, dtype=float)


def select_wall_segment(
    paths: list[Path],
    start_deg: float,
    end_deg: float,
    min_distance_mm: float,
    max_distance_mm: float,
) -> WallSelection:
    all_points, meta = raw_wall_points(paths)
    sources = meta[:, 0].astype(int)
    angles = meta[:, 1]
    distances = meta[:, 2]

    selected_mask = (
        angle_mask(angles, start_deg, end_deg)
        & (distances >= min_distance_mm)
        & (distances <= max_distance_mm)
    )
    selected_points = all_points[selected_mask]
    selected_sources = sources[selected_mask]
    fit = fit_line_pca(selected_points)

    per_run = []
    for idx, path in enumerate(paths):
        mask = selected_sources == idx
        points = selected_points[mask]
        if len(points):
            item_fit = fit_line_pca(points)
            per_run.append({
                "name": path.stem,
                "selected_points": int(len(points)),
                "rmse_mm": item_fit["rmse"],
                "p95_mm": item_fit["p95"],
                "span_mm": item_fit["span"],
                "center": item_fit["center"],
                "direction": item_fit["direction"],
            })
        else:
            per_run.append({
                "name": path.stem,
                "selected_points": 0,
                "rmse_mm": float("nan"),
                "p95_mm": float("nan"),
                "span_mm": float("nan"),
                "center": np.array([float("nan"), float("nan")]),
                "direction": np.array([float("nan"), float("nan")]),
            })

    return WallSelection(
        start_deg=start_deg,
        end_deg=end_deg,
        min_distance_mm=min_distance_mm,
        max_distance_mm=max_distance_mm,
        points=selected_points,
        sources=selected_sources,
        fit=fit,
        per_run=per_run,
    )


def compute_wall_repeat_offset(selection: WallSelection):
    centers = [item["center"] for item in selection.per_run if item["selected_points"] > 0]
    if len(centers) < 2:
        return float("nan")
    center_stack = np.vstack(centers)
    median = np.median(center_stack, axis=0)
    offsets = np.hypot(center_stack[:, 0] - median[0], center_stack[:, 1] - median[1])
    return float(np.max(offsets))


def compute_wall_gap_count(paths: list[Path], selection: WallSelection, threshold_mm: float):
    counts = []
    total = 0
    for source_idx, path in enumerate(paths):
        rows = []
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                try:
                    angle = float(row["angle_deg"]) % 360.0
                    distance_mm = float(row["distance_cm"]) * 10.0
                    x = float(row["x_mm"])
                    y = float(row["y_mm"])
                    t = float(row["host_rx_time_us"])
                except (TypeError, ValueError):
                    continue
                if (
                    angle_mask(np.asarray([angle]), selection.start_deg, selection.end_deg)[0]
                    and selection.min_distance_mm <= distance_mm <= selection.max_distance_mm
                ):
                    rows.append((t, x, y))
        if len(rows) < 2:
            count = 0
        else:
            arr = np.asarray(rows, dtype=float)
            arr = arr[np.argsort(arr[:, 0])]
            gaps = np.hypot(np.diff(arr[:, 1]), np.diff(arr[:, 2]))
            count = int(np.count_nonzero(gaps > threshold_mm))
        total += count
        counts.append({"name": path.stem, "gap_count": count})
    return {"total": total, "per_run": counts}


def save_wall_overlay(paths: list[Path], out: Path):
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    for path, color in zip(paths, colors):
        points, meta = raw_wall_points([path])
        distances = meta[:, 2]
        mask = distances <= 3000.0
        ax.scatter(points[mask, 0], points[mask, 1], s=3, alpha=0.25, label=path.stem, c=color)
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=4)
    ax.set_title("M6 wall overlay, full scan under 3000 mm")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def save_wall_selected(selection: WallSelection, paths: list[Path], out: Path, *, with_fit: bool):
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    for idx, path in enumerate(paths):
        mask = selection.sources == idx
        ax.scatter(selection.points[mask, 0], selection.points[mask, 1], s=7, alpha=0.45, label=path.stem, c=colors[idx])
    if with_fit:
        fit = selection.fit
        center = fit["center"]
        direction = fit["direction"]
        projection = fit["projection"]
        t0 = float(np.min(projection))
        t1 = float(np.max(projection))
        line = np.vstack([center + direction * t0, center + direction * t1])
        ax.plot(line[:, 0], line[:, 1], c="black", linewidth=2, label="wall line fit")
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=3)
    ax.set_title(
        f"M6 wall selected segment: {selection.start_deg:g}->{selection.end_deg:g} deg, "
        f"{selection.min_distance_mm:g}-{selection.max_distance_mm:g} mm"
    )
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def write_markdown(
    run_dir: Path,
    box_repeats: list[RepeatData],
    box_metrics: dict,
    wall_paths: list[Path],
    wall_selection: WallSelection,
    wall_repeat_offset_mm: float,
    wall_gaps: dict,
    image_paths: dict,
):
    metrics_path = run_dir / "geometry_metrics.md"
    strategy_path = run_dir / "strategy_analysis.md"
    tuning_path = run_dir / "tuning_notes.md"

    edge_fit = box_metrics["edge_fit"]
    wall_fit = wall_selection.fit

    metrics_lines = [
        "# M6 Geometry Metrics",
        "",
        "## Box Far Metrics",
        "",
        "| metric | value | note |",
        "| --- | ---: | --- |",
        f"| repeatability_p95_mm | {fmt(box_metrics['repeatability']['repeatability_p95_mm'])} | radial median profile p95 across common 1 deg bins |",
        f"| seam_gap_mm | {fmt(box_metrics['seam']['seam_gap_mm'])} | worst 0/360 median XY seam gap |",
        f"| box_edge_rmse_mm | {fmt(edge_fit['line_rmse_mm'])} | combined four-edge PCA perpendicular RMSE |",
        f"| point_drop_or_gap_count | {box_metrics['gaps']['point_drop_or_gap_count']} | adjacent XY jumps greater than 120 mm |",
        "",
        "### Box Inputs",
        "",
        "| file | raw_points | accepted_points |",
        "| --- | ---: | ---: |",
    ]
    for repeat in box_repeats:
        metrics_lines.append(f"| data/{repeat.path.name} | {repeat.raw_count} | {len(repeat.x)} |")

    metrics_lines.extend([
        "",
        "### Box Edge Details",
        "",
        "| edge | points | rmse_mm | residual_p95_mm | span_mm_p5_to_p95 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for edge in edge_fit["edges"]:
        fit = edge["fit"]
        metrics_lines.append(
            f"| {edge['name']} | {edge['point_count']} | {fmt(fit['rmse'])} | {fmt(fit['p95'])} | {fmt(fit['span'])} |"
        )

    metrics_lines.extend([
        "",
        "### Box Gap Count",
        "",
        "| run | gap_count |",
        "| --- | ---: |",
    ])
    for item in box_metrics["gaps"]["per_run"]:
        metrics_lines.append(f"| {item['name']} | {item['gap_count']} |")

    metrics_lines.extend([
        "",
        "## Wall Metrics",
        "",
        f"- wall_angle_window_deg: `{wall_selection.start_deg:g} -> {wall_selection.end_deg:g}`",
        f"- wall_distance_window_mm: `{wall_selection.min_distance_mm:g} -> {wall_selection.max_distance_mm:g}`",
        "",
        "| metric | value | note |",
        "| --- | ---: | --- |",
        f"| wall_line_rmse_mm | {fmt(wall_fit['rmse'])} | combined wall segment PCA perpendicular RMSE |",
        f"| wall_line_residual_p95_mm | {fmt(wall_fit['p95'])} | p95 absolute perpendicular residual |",
        f"| wall_span_mm_p5_to_p95 | {fmt(wall_fit['span'])} | fitted visible wall span |",
        f"| wall_repeat_offset_mm | {fmt(wall_repeat_offset_mm)} | max run-center offset from median run center |",
        f"| wall_gap_count | {wall_gaps['total']} | adjacent selected wall XY jumps greater than 120 mm |",
        "",
        "### Wall Inputs",
        "",
        "| file | selected_points | line_rmse_mm | residual_p95_mm | span_mm_p5_to_p95 | center_xy_mm |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for item in wall_selection.per_run:
        center = item["center"]
        center_text = f"({fmt(center[0])}, {fmt(center[1])})"
        metrics_lines.append(
            f"| data/{item['name']}.csv | {item['selected_points']} | {fmt(item['rmse_mm'])} | "
            f"{fmt(item['p95_mm'])} | {fmt(item['span_mm'])} | {center_text} |"
        )

    metrics_lines.extend([
        "",
        "### Wall Gap Count",
        "",
        "| run | gap_count |",
        "| --- | ---: |",
    ])
    for item in wall_gaps["per_run"]:
        metrics_lines.append(f"| {item['name']} | {item['gap_count']} |")

    metrics_lines.extend([
        "",
        "## Images",
        "",
    ])
    for key, path in image_paths.items():
        metrics_lines.append(f"- {key}: `assets/{path.name}`")
    metrics_lines.append("")
    metrics_path.write_text("\n".join(metrics_lines), encoding="utf-8")

    strategy_lines = [
        "# M6 Strategy Analysis",
        "",
        "## Observed Phenomena",
        "",
        "- The newer box repeats are cleaner than the first close-box set, but the target is still close enough that edge/near-field effects matter.",
        f"- Box repeatability is {fmt(box_metrics['repeatability']['repeatability_p95_mm'])} mm p95, so the main shape is repeatable at roughly 2 cm scale.",
        f"- Box seam closure is {fmt(box_metrics['seam']['seam_gap_mm'])} mm, so 0/360 closure is not the dominant problem.",
        f"- Box four-edge RMSE is {fmt(edge_fit['line_rmse_mm'])} mm; individual edges show different residuals, so geometry quality is not uniform around the scan.",
        f"- The wall segment is clearly selected at {wall_selection.start_deg:g}->{wall_selection.end_deg:g} deg and has combined RMSE {fmt(wall_fit['rmse'])} mm.",
        "",
        "## Evaluation",
        "",
        "- The system is stable enough for M6 offline analysis: all six CSV files are usable and contain XY fields.",
        "- Single-wall geometry is notably better than box geometry, which suggests the core angle-distance pairing is not grossly broken.",
        "- The box case remains harder because it mixes multiple faces, corners, near-range returns, and occlusion-like gaps.",
        "",
        "## Shortcomings",
        "",
        "- The target distance is still relatively close, so the TF-Luna near-field limit can still affect box edge shape.",
        "- Box edges are not uniformly straight; this points to mounting eccentricity, target placement, edge/corner returns, or filtering, before firmware sync changes.",
        "- Gap counts are still present, so display/analysis should avoid connecting large point jumps as continuous geometry.",
        "- Current wall selection is fixed to the measured window; if the wall moves, the selection window should be re-detected or passed explicitly.",
        "",
        "## Recommended Change Plan",
        "",
        "1. Keep MCU firmware unchanged for now.",
        "2. Keep raw CSV unchanged; apply filtering only in analysis/display paths.",
        "3. Use separate analysis modes: box repeats for whole-shape/four-edge metrics, wall repeats for single-line straightness.",
        "4. Add or keep a configurable wall angle window, currently `350 -> 40` deg for this dataset.",
        "5. In the UI/display layer, avoid connecting adjacent points when XY jump exceeds the gap threshold.",
        "6. If future 60-80 cm wall tests still show high wall RMSE, then investigate angle offset or mounting eccentricity before changing sync logic.",
        "",
    ]
    strategy_path.write_text("\n".join(strategy_lines), encoding="utf-8")

    tuning_lines = [
        "# M6 Tuning Notes",
        "",
        "## Current Data Split",
        "",
        "- Box repeats: `repeat_far_01.csv`, `repeat_far_02.csv`, `repeat_far_03.csv`.",
        "- Wall repeats: `wall_01.csv`, `wall_02.csv`, `wall_03.csv`.",
        "- Wall selection: `angle_deg >= 350` or `angle_deg <= 40`, distance `350-1000 mm`.",
        "",
        "## Current Metrics",
        "",
        "| group | metric | value |",
        "| --- | --- | ---: |",
        f"| box | repeatability_p95_mm | {fmt(box_metrics['repeatability']['repeatability_p95_mm'])} |",
        f"| box | seam_gap_mm | {fmt(box_metrics['seam']['seam_gap_mm'])} |",
        f"| box | box_edge_rmse_mm | {fmt(edge_fit['line_rmse_mm'])} |",
        f"| box | point_drop_or_gap_count | {box_metrics['gaps']['point_drop_or_gap_count']} |",
        f"| wall | wall_line_rmse_mm | {fmt(wall_fit['rmse'])} |",
        f"| wall | wall_line_residual_p95_mm | {fmt(wall_fit['p95'])} |",
        f"| wall | wall_repeat_offset_mm | {fmt(wall_repeat_offset_mm)} |",
        f"| wall | wall_gap_count | {wall_gaps['total']} |",
        "",
        "## Interpretation",
        "",
        "- Wall straightness is good enough to treat the core angle-distance pairing as basically usable.",
        "- Box geometry is repeatable but not uniformly straight across all edges, so keep diagnosing at the analysis/display/mechanical level before firmware changes.",
        "- Seam closure is not the primary issue in this dataset.",
        "",
        "## Next Action",
        "",
        "- Keep MCU firmware unchanged.",
        "- Preserve raw CSV files as evidence.",
        "- Use `tools/m6_group_analysis.py` as the M6 baseline analysis entrypoint.",
        "- If applying display changes later, keep the existing 120 mm large-jump break policy and make it configurable rather than changing raw point coordinates.",
        "",
    ]
    tuning_path.write_text("\n".join(tuning_lines), encoding="utf-8")
    return metrics_path, strategy_path, tuning_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--box-max-distance-cm", type=float, default=100.0)
    parser.add_argument("--box-edge-percentile", type=float, default=5.0)
    parser.add_argument("--box-edge-band-mm", type=float, default=35.0)
    parser.add_argument("--wall-start-deg", type=float, default=350.0)
    parser.add_argument("--wall-end-deg", type=float, default=40.0)
    parser.add_argument("--wall-min-distance-mm", type=float, default=350.0)
    parser.add_argument("--wall-max-distance-mm", type=float, default=1000.0)
    parser.add_argument("--gap-threshold-mm", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_dir = args.run_dir.resolve()
    data_dir = run_dir / "data"
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    box_names = ["repeat_far_01.csv", "repeat_far_02.csv", "repeat_far_03.csv"]
    wall_names = ["wall_01.csv", "wall_02.csv", "wall_03.csv"]
    wall_paths = [data_dir / name for name in wall_names]

    box_repeats = load_named_repeats(data_dir, box_names, args.box_max_distance_cm)
    repeatability = compute_repeatability(box_repeats, bin_width_deg=1.0, min_bin_points=3)
    seam = compute_seam_gaps(box_repeats, seam_window_deg=2.0)
    gaps = compute_gap_counts(box_repeats, gap_threshold_mm=args.gap_threshold_mm)
    edge_fit = select_box_edges(
        box_repeats,
        edge_percentile=args.box_edge_percentile,
        edge_band_mm=args.box_edge_band_mm,
        min_points=120,
    )
    box_metrics = {
        "repeatability": repeatability,
        "seam": seam,
        "gaps": gaps,
        "edge_fit": edge_fit,
    }

    wall_selection = select_wall_segment(
        wall_paths,
        start_deg=args.wall_start_deg,
        end_deg=args.wall_end_deg,
        min_distance_mm=args.wall_min_distance_mm,
        max_distance_mm=args.wall_max_distance_mm,
    )
    wall_repeat_offset_mm = compute_wall_repeat_offset(wall_selection)
    wall_gaps = compute_wall_gap_count(wall_paths, wall_selection, threshold_mm=args.gap_threshold_mm)

    image_paths = {
        "box_far_overlay": save_scatter_overlay(box_repeats, assets_dir / "box_far_overlay.png", "M6 box far repeat overlay"),
        "box_far_edge_fit": save_box_edge_fit(box_repeats, edge_fit, assets_dir / "box_far_edge_fit.png"),
        "box_far_seam_closeup": save_seam_closeup(box_repeats, assets_dir / "box_far_seam_closeup.png", seam_window_deg=2.0),
        "wall_overlay": save_wall_overlay(wall_paths, assets_dir / "wall_overlay.png"),
        "wall_selected_segment": save_wall_selected(wall_selection, wall_paths, assets_dir / "wall_selected_segment.png", with_fit=False),
        "wall_line_fit": save_wall_selected(wall_selection, wall_paths, assets_dir / "wall_line_fit.png", with_fit=True),
    }

    metrics_path, strategy_path, tuning_path = write_markdown(
        run_dir,
        box_repeats,
        box_metrics,
        wall_paths,
        wall_selection,
        wall_repeat_offset_mm,
        wall_gaps,
        image_paths,
    )

    for key, path in image_paths.items():
        print(f"{key}={path}")
    print(f"metrics={metrics_path}")
    print(f"strategy={strategy_path}")
    print(f"tuning={tuning_path}")


if __name__ == "__main__":
    raise SystemExit(main())
