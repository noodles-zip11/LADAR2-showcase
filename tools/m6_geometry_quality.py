#!/usr/bin/env python3
"""Generate M6 geometry quality plots and metrics from repeat CSV files."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual"


@dataclass
class RepeatData:
    name: str
    path: Path
    raw_count: int
    x: np.ndarray
    y: np.ndarray
    angle_deg: np.ndarray
    distance_mm: np.ndarray
    host_rx_time_us: np.ndarray


def circular_delta_deg(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def percentile(values, p):
    if len(values) == 0:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), p))


def load_repeat(path: Path, max_distance_cm: float) -> RepeatData:
    xs = []
    ys = []
    angles = []
    distances = []
    times = []
    raw_count = 0

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"host_rx_time_us", "angle_deg", "distance_cm", "x_mm", "y_mm"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} missing fields: {sorted(missing)}")

        for row in reader:
            raw_count += 1
            try:
                x = float(row["x_mm"])
                y = float(row["y_mm"])
                angle = float(row["angle_deg"]) % 360.0
                distance_cm = float(row["distance_cm"])
                host_rx_time_us = float(row["host_rx_time_us"])
            except (TypeError, ValueError):
                continue

            if not all(math.isfinite(v) for v in (x, y, angle, distance_cm, host_rx_time_us)):
                continue
            if distance_cm <= 0.0 or distance_cm > max_distance_cm:
                continue

            xs.append(x)
            ys.append(y)
            angles.append(angle)
            distances.append(distance_cm * 10.0)
            times.append(host_rx_time_us)

    return RepeatData(
        name=path.stem,
        path=path,
        raw_count=raw_count,
        x=np.asarray(xs, dtype=float),
        y=np.asarray(ys, dtype=float),
        angle_deg=np.asarray(angles, dtype=float),
        distance_mm=np.asarray(distances, dtype=float),
        host_rx_time_us=np.asarray(times, dtype=float),
    )


def angle_mask(angles, start_deg, end_deg):
    angles = np.asarray(angles) % 360.0
    start_deg %= 360.0
    end_deg %= 360.0
    if start_deg <= end_deg:
        return (angles >= start_deg) & (angles <= end_deg)
    return (angles >= start_deg) | (angles <= end_deg)


def radial_profile(repeat: RepeatData, bin_width_deg: float, min_bin_points: int):
    bins = np.floor(repeat.angle_deg / bin_width_deg).astype(int)
    profile = {}
    counts = {}
    for bin_id in np.unique(bins):
        mask = bins == bin_id
        if int(mask.sum()) >= min_bin_points:
            profile[int(bin_id)] = float(np.median(repeat.distance_mm[mask]))
            counts[int(bin_id)] = int(mask.sum())
    return profile, counts


def compute_repeatability(repeats, bin_width_deg, min_bin_points):
    profiles = []
    for repeat in repeats:
        profile, _counts = radial_profile(repeat, bin_width_deg, min_bin_points)
        profiles.append(profile)

    common_bins = set(profiles[0])
    for profile in profiles[1:]:
        common_bins &= set(profile)
    common_bins = sorted(common_bins)

    deviations = []
    for bin_id in common_bins:
        vals = np.asarray([profile[bin_id] for profile in profiles], dtype=float)
        median = float(np.median(vals))
        deviations.extend(np.abs(vals - median))

    return {
        "repeatability_p95_mm": percentile(deviations, 95),
        "common_angle_bins": len(common_bins),
        "deviation_count": len(deviations),
    }


def compute_seam_gaps(repeats, seam_window_deg):
    per_run = []
    gaps = []
    for repeat in repeats:
        low_mask = repeat.angle_deg <= seam_window_deg
        high_mask = repeat.angle_deg >= (360.0 - seam_window_deg)
        if int(low_mask.sum()) == 0 or int(high_mask.sum()) == 0:
            gap = float("nan")
            low_xy = (float("nan"), float("nan"))
            high_xy = (float("nan"), float("nan"))
        else:
            low_xy = (float(np.median(repeat.x[low_mask])), float(np.median(repeat.y[low_mask])))
            high_xy = (float(np.median(repeat.x[high_mask])), float(np.median(repeat.y[high_mask])))
            gap = float(math.hypot(low_xy[0] - high_xy[0], low_xy[1] - high_xy[1]))
            gaps.append(gap)
        per_run.append({
            "name": repeat.name,
            "low_count": int(low_mask.sum()),
            "high_count": int(high_mask.sum()),
            "low_xy": low_xy,
            "high_xy": high_xy,
            "gap_mm": gap,
        })

    return {
        "seam_gap_mm": max(gaps) if gaps else float("nan"),
        "per_run": per_run,
    }


def compute_gap_counts(repeats, gap_threshold_mm):
    per_run = []
    total = 0
    for repeat in repeats:
        if len(repeat.x) < 2:
            count = 0
        else:
            order = np.argsort(repeat.host_rx_time_us)
            x = repeat.x[order]
            y = repeat.y[order]
            dx = np.diff(x)
            dy = np.diff(y)
            gaps = np.hypot(dx, dy)
            count = int(np.count_nonzero(gaps > gap_threshold_mm))
        total += count
        per_run.append({"name": repeat.name, "gap_count": count})
    return {"point_drop_or_gap_count": total, "per_run": per_run}


def fit_line_pca(points):
    center = points.mean(axis=0)
    centered = points - center
    _u, _s, vh = np.linalg.svd(centered, full_matrices=False)
    direction = vh[0]
    normal = np.array([-direction[1], direction[0]])
    residuals = centered @ normal
    projection = centered @ direction
    rmse = float(math.sqrt(np.mean(residuals ** 2)))
    p95 = percentile(np.abs(residuals), 95)
    span = percentile(projection, 95) - percentile(projection, 5)
    return {
        "center": center,
        "direction": direction,
        "normal": normal,
        "residuals": residuals,
        "projection": projection,
        "rmse": rmse,
        "p95": p95,
        "span": float(span),
    }


def select_box_edges(repeats, edge_percentile, edge_band_mm, min_points):
    points_all = []
    source_all = []
    for idx, repeat in enumerate(repeats):
        points_all.append(np.column_stack([repeat.x, repeat.y]))
        source_all.append(np.full(len(repeat.x), idx, dtype=int))

    points_all = np.vstack(points_all)
    source_all = np.concatenate(source_all)
    x = points_all[:, 0]
    y = points_all[:, 1]
    bounds = {
        "left": float(np.percentile(x, edge_percentile)),
        "right": float(np.percentile(x, 100.0 - edge_percentile)),
        "bottom": float(np.percentile(y, edge_percentile)),
        "top": float(np.percentile(y, 100.0 - edge_percentile)),
    }

    edge_defs = [
        ("left", x <= bounds["left"] + edge_band_mm),
        ("right", x >= bounds["right"] - edge_band_mm),
        ("bottom", y <= bounds["bottom"] + edge_band_mm),
        ("top", y >= bounds["top"] - edge_band_mm),
    ]

    edges = []
    residuals = []
    for name, mask in edge_defs:
        edge_points = points_all[mask]
        if len(edge_points) < min_points:
            continue
        fit = fit_line_pca(edge_points)
        edges.append({
            "name": name,
            "points": edge_points,
            "sources": source_all[mask],
            "fit": fit,
            "point_count": int(len(edge_points)),
        })
        residuals.extend(fit["residuals"].tolist())

    if not edges:
        raise ValueError("could not select box edge bands")

    residuals = np.asarray(residuals, dtype=float)
    return {
        "edges": edges,
        "bounds": bounds,
        "line_rmse_mm": float(math.sqrt(np.mean(residuals ** 2))),
        "line_residual_p95_mm": percentile(np.abs(residuals), 95),
        "point_count": int(sum(edge["point_count"] for edge in edges)),
        "edge_percentile": float(edge_percentile),
        "edge_band_mm": float(edge_band_mm),
    }


def select_line_segment(repeats, min_points):
    points_all = []
    angles_all = []
    source_all = []
    for idx, repeat in enumerate(repeats):
        points = np.column_stack([repeat.x, repeat.y])
        points_all.append(points)
        angles_all.append(repeat.angle_deg)
        source_all.append(np.full(len(repeat.x), idx, dtype=int))

    points_all = np.vstack(points_all)
    angles_all = np.concatenate(angles_all)
    source_all = np.concatenate(source_all)

    best = None
    for width in (20.0, 30.0, 45.0, 60.0):
        for center in np.arange(0.0, 360.0, 5.0):
            start = center - width / 2.0
            end = center + width / 2.0
            mask = angle_mask(angles_all, start, end)
            n = int(mask.sum())
            if n < min_points:
                continue
            fit = fit_line_pca(points_all[mask])
            if fit["span"] < 150.0:
                continue
            score = fit["rmse"] / max(1.0, min(fit["span"], 1200.0) / 1200.0)
            if best is None or score < best["score"]:
                best = {
                    "score": float(score),
                    "center_deg": float(center % 360.0),
                    "start_deg": float(start % 360.0),
                    "end_deg": float(end % 360.0),
                    "width_deg": float(width),
                    "mask": mask,
                    "points": points_all[mask],
                    "sources": source_all[mask],
                    "fit": fit,
                    "point_count": n,
                }

    if best is None:
        raise ValueError("could not select a line-like segment")
    return best


def set_equal_axes(ax):
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x_mm")
    ax.set_ylabel("y_mm")


def save_repeat_overlay(repeats, assets_dir):
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    for repeat, color in zip(repeats, colors):
        ax.scatter(repeat.x, repeat.y, s=2, alpha=0.35, label=f"{repeat.name} ({len(repeat.x)} pts)", c=color)
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=4)
    ax.set_title("M6 repeat overlay")
    fig.tight_layout()
    out = assets_dir / "repeat_overlay.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def save_seam_closeup(repeats, assets_dir, seam_window_deg):
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    xs = []
    ys = []
    for repeat, color in zip(repeats, colors):
        mask = (repeat.angle_deg <= seam_window_deg) | (repeat.angle_deg >= (360.0 - seam_window_deg))
        ax.scatter(repeat.x[mask], repeat.y[mask], s=8, alpha=0.55, label=repeat.name, c=color)
        if int(mask.sum()):
            xs.extend(repeat.x[mask].tolist())
            ys.extend(repeat.y[mask].tolist())
    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=3)
    ax.set_title(f"M6 seam closeup: angle <= {seam_window_deg:g} or >= {360 - seam_window_deg:g} deg")
    if xs and ys:
        pad = 80.0
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    fig.tight_layout()
    out = assets_dir / "seam_closeup.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def save_line_fit(repeats, assets_dir, line_segment):
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c")
    line_colors = {
        "left": "#111111",
        "right": "#7f7f7f",
        "bottom": "#8c564b",
        "top": "#9467bd",
    }

    for edge_index, edge in enumerate(line_segment["edges"]):
        points = edge["points"]
        sources = edge["sources"]
        for idx, repeat in enumerate(repeats):
            mask = sources == idx
            label = repeat.name if edge_index == 0 else None
            ax.scatter(points[mask, 0], points[mask, 1], s=4, alpha=0.25, label=label, c=colors[idx])

        fit = edge["fit"]
        center = fit["center"]
        direction = fit["direction"]
        projection = fit["projection"]
        t0 = float(np.min(projection))
        t1 = float(np.max(projection))
        line = np.vstack([center + direction * t0, center + direction * t1])
        ax.plot(
            line[:, 0],
            line[:, 1],
            c=line_colors.get(edge["name"], "black"),
            linewidth=2,
            label=f"{edge['name']} edge fit",
        )

    set_equal_axes(ax)
    ax.legend(loc="best", markerscale=3)
    ax.set_title("M6 box edge line fit")
    fig.tight_layout()
    out = assets_dir / "line_fit.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def fmt(value, digits=2):
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    return f"{float(value):.{digits}f}"


def write_metrics(run_dir, repeats, repeatability, seam, gaps, line_segment, params, image_paths):
    metrics_path = run_dir / "geometry_metrics.md"
    line_rmse_mm = line_segment["line_rmse_mm"]

    lines = [
        "# M6 Geometry Metrics",
        "",
        "## Summary",
        "",
        "| metric | value | note |",
        "| --- | ---: | --- |",
        f"| repeatability_p95_mm | {fmt(repeatability['repeatability_p95_mm'])} | radial median profile p95 across common 1 deg bins |",
        f"| seam_gap_mm | {fmt(seam['seam_gap_mm'])} | worst per-run median XY gap between 0 deg and 360 deg windows |",
        f"| line_rmse_mm | {fmt(line_rmse_mm)} | combined PCA perpendicular RMSE across detected box edge bands |",
        f"| point_drop_or_gap_count | {gaps['point_drop_or_gap_count']} | adjacent accepted XY jumps greater than {params['gap_threshold_mm']:.0f} mm |",
        "",
        "## Inputs",
        "",
        "| file | raw_points | accepted_points |",
        "| --- | ---: | ---: |",
    ]
    for repeat in repeats:
        lines.append(f"| data/{repeat.path.name} | {repeat.raw_count} | {len(repeat.x)} |")

    lines.extend([
        "",
        "## Per-Run Seam",
        "",
        "| run | low_count | high_count | seam_gap_mm | low_xy_mm | high_xy_mm |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ])
    for item in seam["per_run"]:
        low_xy = f"({fmt(item['low_xy'][0])}, {fmt(item['low_xy'][1])})"
        high_xy = f"({fmt(item['high_xy'][0])}, {fmt(item['high_xy'][1])})"
        lines.append(
            f"| {item['name']} | {item['low_count']} | {item['high_count']} | "
            f"{fmt(item['gap_mm'])} | {low_xy} | {high_xy} |"
        )

    lines.extend([
        "",
        "## Per-Run Gap Count",
        "",
        "| run | gap_count |",
        "| --- | ---: |",
    ])
    for item in gaps["per_run"]:
        lines.append(f"| {item['name']} | {item['gap_count']} |")

    lines.extend([
        "",
        "## Box Edge Line Fit",
        "",
        f"- selected edge points: {line_segment['point_count']}",
        f"- line_rmse_mm: {fmt(line_segment['line_rmse_mm'])}",
        f"- line_residual_p95_mm: {fmt(line_segment['line_residual_p95_mm'])}",
        f"- edge_percentile: {line_segment['edge_percentile']:.1f}",
        f"- edge_band_mm: {line_segment['edge_band_mm']:.1f}",
        "",
        "| edge | points | rmse_mm | residual_p95_mm | span_mm_p5_to_p95 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for edge in line_segment["edges"]:
        fit = edge["fit"]
        lines.append(
            f"| {edge['name']} | {edge['point_count']} | {fmt(fit['rmse'])} | "
            f"{fmt(fit['p95'])} | {fmt(fit['span'])} |"
        )

    lines.extend([
        "",
        "## Images",
        "",
    ])
    for name, path in image_paths.items():
        lines.append(f"- {name}: `assets/{path.name}`")

    lines.extend([
        "",
        "## Analysis Parameters",
        "",
        f"- max_distance_cm: {params['max_distance_cm']:.0f}",
        f"- repeatability_bin_width_deg: {params['bin_width_deg']:.1f}",
        f"- repeatability_min_bin_points: {params['min_bin_points']}",
        f"- seam_window_deg: {params['seam_window_deg']:.1f}",
        f"- gap_threshold_mm: {params['gap_threshold_mm']:.0f}",
        f"- box_edge_percentile: {params['box_edge_percentile']:.1f}",
        f"- box_edge_band_mm: {params['box_edge_band_mm']:.1f}",
        "",
    ])
    metrics_path.write_text("\n".join(lines), encoding="utf-8")
    return metrics_path


def write_tuning_notes(run_dir, repeatability, seam, gaps, line_segment):
    notes_path = run_dir / "tuning_notes.md"
    lines = [
        "# M6 Tuning Notes",
        "",
        "## First Pass Conclusion",
        "",
        "- The three repeat CSV files were accepted and analyzed without changing the raw data.",
        f"- repeatability_p95_mm = {fmt(repeatability['repeatability_p95_mm'])}.",
        f"- seam_gap_mm = {fmt(seam['seam_gap_mm'])}.",
        f"- line_rmse_mm = {fmt(line_segment['line_rmse_mm'])}.",
        f"- point_drop_or_gap_count = {gaps['point_drop_or_gap_count']}.",
        "",
        "## Next Tuning Target",
        "",
    ]
    if math.isfinite(seam["seam_gap_mm"]) and seam["seam_gap_mm"] > 80.0:
        lines.append("- Start with 0/360 degree boundary handling and sweep connection policy.")
    elif math.isfinite(line_segment["line_rmse_mm"]) and line_segment["line_rmse_mm"] > 50.0:
        lines.append("- Start with box-edge diagnosis: angle offset, mounting eccentricity, or local outlier filtering.")
    elif gaps["point_drop_or_gap_count"] > 0:
        lines.append("- Start with gap/jump review in the plotted line segment and seam area.")
    else:
        lines.append("- No single severe issue dominates from the automatic metrics; review the three plots visually first.")
    lines.append("")
    notes_path.write_text("\n".join(lines), encoding="utf-8")
    return notes_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--max-distance-cm", type=float, default=100.0)
    parser.add_argument("--bin-width-deg", type=float, default=1.0)
    parser.add_argument("--min-bin-points", type=int, default=3)
    parser.add_argument("--seam-window-deg", type=float, default=2.0)
    parser.add_argument("--gap-threshold-mm", type=float, default=120.0)
    parser.add_argument("--line-min-points", type=int, default=150)
    parser.add_argument("--box-edge-percentile", type=float, default=5.0)
    parser.add_argument("--box-edge-band-mm", type=float, default=35.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_dir = args.run_dir.resolve()
    data_dir = run_dir / "data"
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = sorted(data_dir.glob("repeat_0*.csv"))
    if len(csv_paths) < 3:
        raise SystemExit(f"expected at least 3 repeat CSV files under {data_dir}, found {len(csv_paths)}")
    csv_paths = csv_paths[:3]

    repeats = [load_repeat(path, args.max_distance_cm) for path in csv_paths]
    for repeat in repeats:
        if len(repeat.x) == 0:
            raise SystemExit(f"{repeat.path} has no accepted points")

    params = {
        "max_distance_cm": args.max_distance_cm,
        "bin_width_deg": args.bin_width_deg,
        "min_bin_points": args.min_bin_points,
        "seam_window_deg": args.seam_window_deg,
        "gap_threshold_mm": args.gap_threshold_mm,
        "box_edge_percentile": args.box_edge_percentile,
        "box_edge_band_mm": args.box_edge_band_mm,
    }

    repeatability = compute_repeatability(repeats, args.bin_width_deg, args.min_bin_points)
    seam = compute_seam_gaps(repeats, args.seam_window_deg)
    gaps = compute_gap_counts(repeats, args.gap_threshold_mm)
    line_segment = select_box_edges(
        repeats,
        edge_percentile=args.box_edge_percentile,
        edge_band_mm=args.box_edge_band_mm,
        min_points=args.line_min_points,
    )

    image_paths = {
        "repeat_overlay": save_repeat_overlay(repeats, assets_dir),
        "seam_closeup": save_seam_closeup(repeats, assets_dir, args.seam_window_deg),
        "line_fit": save_line_fit(repeats, assets_dir, line_segment),
    }

    metrics_path = write_metrics(run_dir, repeats, repeatability, seam, gaps, line_segment, params, image_paths)
    notes_path = write_tuning_notes(run_dir, repeatability, seam, gaps, line_segment)

    print(f"repeat_overlay={image_paths['repeat_overlay']}")
    print(f"seam_closeup={image_paths['seam_closeup']}")
    print(f"line_fit={image_paths['line_fit']}")
    print(f"metrics={metrics_path}")
    print(f"tuning_notes={notes_path}")


if __name__ == "__main__":
    raise SystemExit(main())
