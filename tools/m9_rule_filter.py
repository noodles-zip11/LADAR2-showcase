#!/usr/bin/env python3
"""M9 rule-based point quality filter.

This is an offline-only M9 tool. It consumes the M8 replay CSV contract,
marks rule-level anomaly candidates, writes a filtered CSV, and produces
Markdown/PNG evidence for before-vs-after comparison.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY_ROOT = REPO_ROOT / "docs" / "m8" / "datasets" / "replay_sets"
DEFAULT_KNOWN_SCENE_ROOT = REPO_ROOT / "docs" / "m8" / "datasets" / "known_scenes"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "docs" / "m9" / "runs" / "rule_based_v1"

REQUIRED_FIELDS = ("host_rx_time_us", "angle_deg", "distance_cm")
OPTIONAL_NUMERIC_FIELDS = ("t_sample_us", "angle_tick", "x_mm", "y_mm", "quality", "status")

STATUS_ALERT_MASK = 0x07
STATUS_ESTIMATED_FLAG = 0x08


@dataclass(frozen=True)
class RuleConfig:
    low_quality_threshold: float = 10.0
    max_neighbor_angle_gap_deg: float = 3.0
    max_neighbor_time_gap_us: float = 120_000.0
    distance_jump_cm: float = 80.0
    distance_jump_ratio: float = 0.60
    isolated_distance_delta_cm: float = 80.0
    stability_angle_bin_deg: float = 2.0
    stability_min_bin_points: int = 8
    stability_delta_cm: float = 90.0
    stability_mad_multiplier: float = 6.0


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def parse_int(value: str | None) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def load_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        missing = set(REQUIRED_FIELDS) - set(fieldnames)
        if missing:
            raise ValueError(f"{path} missing required fields: {sorted(missing)}")

        rows: list[dict[str, Any]] = []
        for row_index, raw in enumerate(reader, start=2):
            row: dict[str, Any] = {
                "source_row": row_index,
                "raw": dict(raw),
                "host_rx_time_us": parse_float(raw.get("host_rx_time_us")),
                "angle_deg": parse_float(raw.get("angle_deg")),
                "distance_cm": parse_float(raw.get("distance_cm")),
            }
            for field in OPTIONAL_NUMERIC_FIELDS:
                row[field] = parse_float(raw.get(field))
            row["valid_input"] = all(row[field] is not None for field in REQUIRED_FIELDS)
            if row["angle_deg"] is not None:
                row["angle_deg"] = float(row["angle_deg"]) % 360.0
            rows.append(row)
    return rows, fieldnames


def status_alert(status: float | None) -> bool:
    if status is None:
        return False
    return (int(status) & STATUS_ALERT_MASK) != 0


def has_estimated_flag(status: float | None) -> bool:
    if status is None:
        return False
    return (int(status) & STATUS_ESTIMATED_FLAG) != 0


def angular_gap(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


def distance_jump(a: float, b: float, config: RuleConfig) -> bool:
    delta = abs(a - b)
    base = min(abs(a), abs(b))
    return delta > config.distance_jump_cm and (base <= 0.0 or delta / base > config.distance_jump_ratio)


def compute_stability_bins(rows: list[dict[str, Any]], config: RuleConfig) -> dict[int, dict[str, float]]:
    per_bin: dict[int, list[float]] = {}
    for row in rows:
        if not row["valid_input"]:
            continue
        distance = float(row["distance_cm"])
        if distance <= 0.0:
            continue
        bin_id = int(float(row["angle_deg"]) // config.stability_angle_bin_deg)
        per_bin.setdefault(bin_id, []).append(distance)

    stats: dict[int, dict[str, float]] = {}
    for bin_id, distances in per_bin.items():
        if len(distances) < config.stability_min_bin_points:
            continue
        median = statistics.median(distances)
        deviations = [abs(value - median) for value in distances]
        mad = statistics.median(deviations)
        stats[bin_id] = {
            "median": median,
            "mad": mad,
            "threshold": max(config.stability_delta_cm, config.stability_mad_multiplier * mad),
        }
    return stats


def classify_rows(rows: list[dict[str, Any]], config: RuleConfig) -> list[dict[str, Any]]:
    stability_bins = compute_stability_bins(rows, config)
    results: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        reasons: list[str] = []
        if not row["valid_input"]:
            reasons.append("invalid_input")
        else:
            distance = float(row["distance_cm"])
            quality = row.get("quality")
            status = row.get("status")

            if distance <= 0.0:
                reasons.append("nonpositive_distance")
            if quality is not None and float(quality) < config.low_quality_threshold:
                reasons.append("low_quality")
            if status_alert(status):
                reasons.append("status_alert")

            neighbor_deltas: list[float] = []
            jump_neighbors = 0
            close_neighbors = 0
            for neighbor_index in (index - 1, index + 1):
                if neighbor_index < 0 or neighbor_index >= len(rows):
                    continue
                neighbor = rows[neighbor_index]
                if not neighbor["valid_input"]:
                    continue
                angle_gap = angular_gap(float(row["angle_deg"]), float(neighbor["angle_deg"]))
                time_gap = abs(float(row["host_rx_time_us"]) - float(neighbor["host_rx_time_us"]))
                if (
                    angle_gap <= config.max_neighbor_angle_gap_deg
                    or time_gap <= config.max_neighbor_time_gap_us
                ):
                    close_neighbors += 1
                    delta = abs(distance - float(neighbor["distance_cm"]))
                    neighbor_deltas.append(delta)
                    if distance_jump(distance, float(neighbor["distance_cm"]), config):
                        jump_neighbors += 1

            if jump_neighbors:
                reasons.append("distance_jump")
            if close_neighbors == 0:
                reasons.append("isolated_no_neighbor")
            elif neighbor_deltas and min(neighbor_deltas) > config.isolated_distance_delta_cm:
                reasons.append("isolated_distance")

            bin_id = int(float(row["angle_deg"]) // config.stability_angle_bin_deg)
            bin_stats = stability_bins.get(bin_id)
            if bin_stats and abs(distance - bin_stats["median"]) > bin_stats["threshold"]:
                reasons.append("unstable_angle_bin")

        results.append(
            {
                "source_row": row["source_row"],
                "keep": 0 if reasons else 1,
                "m9_reasons": ";".join(reasons),
                "valid_input": 1 if row["valid_input"] else 0,
                "estimated_flag": 1 if has_estimated_flag(row.get("status")) else 0,
                "raw": row["raw"],
            }
        )
    return results


def summarize(rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    for result in results:
        for reason in result["m9_reasons"].split(";"):
            if reason:
                reason_counts[reason] += 1

    kept = [result for result in results if result["keep"] == 1]
    flagged = len(results) - len(kept)
    valid_inputs = sum(1 for result in results if result["valid_input"] == 1)
    status_estimated = sum(1 for result in results if result["estimated_flag"] == 1)

    continuity_denominator = max(valid_inputs, 1)
    continuity_breaks = (
        reason_counts["distance_jump"]
        + reason_counts["isolated_no_neighbor"]
        + reason_counts["isolated_distance"]
    )
    stability_breaks = reason_counts["unstable_angle_bin"]

    return {
        "total_rows": len(results),
        "valid_inputs": valid_inputs,
        "kept_points": len(kept),
        "filtered_points": flagged,
        "filtered_ratio": flagged / len(results) if results else 0.0,
        "status_estimated_count": status_estimated,
        "status_estimated_ratio": status_estimated / len(results) if results else 0.0,
        "continuity_issue_count": continuity_breaks,
        "continuity_issue_ratio": continuity_breaks / continuity_denominator,
        "stability_issue_count": stability_breaks,
        "stability_issue_ratio": stability_breaks / continuity_denominator,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def write_filtered_csv(path: Path, fieldnames: list[str], results: list[dict[str, Any]]) -> None:
    output_fields = fieldnames + ["m9_keep", "m9_reasons"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        for result in results:
            row = dict(result["raw"])
            row["m9_keep"] = result["keep"]
            row["m9_reasons"] = result["m9_reasons"]
            writer.writerow(row)


def format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_report(dataset_name: str, input_path: Path, filtered_path: Path, summary: dict[str, Any]) -> str:
    display_input = display_path(input_path)
    display_filtered = display_path(filtered_path)
    lines = [
        f"# M9 Rule Quality Gate Appendix Report - {dataset_name}",
        "",
        f"- Input: `{display_input}`",
        f"- Filtered CSV: `{display_filtered}`",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key in (
        "total_rows",
        "valid_inputs",
        "kept_points",
        "filtered_points",
        "filtered_ratio",
        "status_estimated_count",
        "status_estimated_ratio",
        "continuity_issue_count",
        "continuity_issue_ratio",
        "stability_issue_count",
        "stability_issue_ratio",
    ):
        lines.append(f"| `{key}` | {format_value(summary[key])} |")

    lines.extend(["", "## Rule Reasons", "", "| reason | count |", "| --- | ---: |"])
    reason_counts = summary["reason_counts"]
    if reason_counts:
        for reason, count in reason_counts.items():
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("| n/a | 0 |")

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This is rule-level point quality screening, not scene ground truth.",
            "- `status=0x08` is tracked as an estimated flag and is not treated as an alert by itself.",
            "- The stability rule uses repeated distance behavior within angle bins; moving targets or changed scenes still need manual labels.",
        ]
    )
    return "\n".join(lines) + "\n"


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_plot(path: Path, rows: list[dict[str, Any]], results: list[dict[str, Any]], title: str) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    kept_x: list[float] = []
    kept_y: list[float] = []
    flagged_x: list[float] = []
    flagged_y: list[float] = []

    for row, result in zip(rows, results):
        if not row["valid_input"] or float(row["distance_cm"]) <= 0.0:
            continue
        angle = math.radians(float(row["angle_deg"]))
        distance = float(row["distance_cm"])
        x = distance * math.cos(angle)
        y = distance * math.sin(angle)
        if result["keep"]:
            kept_x.append(x)
            kept_y.append(y)
        else:
            flagged_x.append(x)
            flagged_y.append(y)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(kept_x, kept_y, s=3, c="#2563eb", alpha=0.55, label="kept")
    if flagged_x:
        ax.scatter(flagged_x, flagged_y, s=8, c="#dc2626", alpha=0.8, label="filtered")
    ax.set_title(title)
    ax.set_xlabel("x cm")
    ax.set_ylabel("y cm")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.4, alpha=0.4)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def analyze_file(input_path: Path, output_dir: Path, config: RuleConfig) -> dict[str, Any]:
    rows, fieldnames = load_rows(input_path)
    results = classify_rows(rows, config)
    summary = summarize(rows, results)

    dataset_name = input_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    filtered_path = output_dir / f"{dataset_name}.m9_filtered.csv"
    report_path = output_dir / f"{dataset_name}.m9_report.md"
    plot_path = output_dir / f"{dataset_name}.m9_compare.png"

    write_filtered_csv(filtered_path, fieldnames, results)
    report_path.write_text(render_report(dataset_name, input_path, filtered_path, summary), encoding="utf-8")
    plot_written = write_plot(plot_path, rows, results, f"{dataset_name} M9 quality gate appendix")

    return {
        "dataset": dataset_name,
        "input": input_path,
        "output_dir": output_dir,
        "filtered_csv": filtered_path,
        "report": report_path,
        "plot": plot_path if plot_written else None,
        "summary": summary,
    }


def discover_dataset_csvs(dataset_root: Path) -> list[Path]:
    csvs: list[Path] = []
    if not dataset_root.exists():
        return csvs
    for dataset_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        csv_path = dataset_dir / f"{dataset_dir.name}.csv"
        if csv_path.exists():
            csvs.append(csv_path)
    return csvs


def discover_replay_csvs(replay_root: Path) -> list[Path]:
    return discover_dataset_csvs(replay_root)


def render_group_table(title: str, entries: list[dict[str, Any]], *, base_dir: Path) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| dataset | total | kept | filtered | filtered ratio | continuity issue ratio | stability issue ratio | report | plot |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    if not entries:
        lines.append("| n/a | 0 | 0 | 0 | 0 | 0 | 0 | n/a | n/a |")
        return lines

    for entry in entries:
        summary = entry["summary"]
        report_link = f"{entry['dataset']}/{Path(entry['report']).name}"
        plot_link = f"{entry['dataset']}/{Path(entry['plot']).name}" if entry["plot"] else "n/a"
        lines.append(
            f"| `{entry['dataset']}` "
            f"| {summary['total_rows']} "
            f"| {summary['kept_points']} "
            f"| {summary['filtered_points']} "
            f"| {format_value(summary['filtered_ratio'])} "
            f"| {format_value(summary['continuity_issue_ratio'])} "
            f"| {format_value(summary['stability_issue_ratio'])} "
            f"| [report]({base_dir.name}/{report_link}) "
            f"| [plot]({base_dir.name}/{plot_link}) |"
        )
    return lines


def aggregate(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(entry["summary"]["total_rows"]) for entry in entries)
    filtered = sum(int(entry["summary"]["filtered_points"]) for entry in entries)
    kept = sum(int(entry["summary"]["kept_points"]) for entry in entries)
    return {
        "total": total,
        "kept": kept,
        "filtered": filtered,
        "filtered_ratio": filtered / total if total else 0.0,
    }


def render_index(replay_entries: list[dict[str, Any]], known_entries: list[dict[str, Any]]) -> str:
    lines = [
        "# M9 Rule Quality Gate Appendix",
        "",
        "M9 is an offline rule-based point quality filter built on the M8 dataset contract.",
        "It does not train a model, does not use AI, and does not change the live CAN/MCU path.",
        "The results are separated so unknown replay captures are not used as scene-level evidence.",
        "",
        "## Rule Set",
        "",
        "- Distance jump: flags unreasonable short-neighbor distance changes.",
        "- Neighborhood continuity: flags points without close neighbors or with only far-distance neighbors.",
        "- Quality/status: flags low quality and non-zero alert levels from `status & 0x07`.",
        "- Multi-scan stability: flags points that deviate from the repeated distance behavior of the same angle bin.",
        "",
    ]

    lines.extend(render_group_table("Unknown Replay Results", replay_entries, base_dir=Path("replay_sets")))
    lines.extend([""])
    lines.extend(render_group_table("Known Scene Results", known_entries, base_dir=Path("known_scenes")))

    replay_total = aggregate(replay_entries)
    known_total = aggregate(known_entries)

    lines.extend(
        [
            "",
            "## V1 Conclusion",
            "",
            f"- Unknown replay rows processed: `{replay_total['total']}`; filtered candidates: `{replay_total['filtered']}` (`{format_value(replay_total['filtered_ratio'])}`).",
            f"- Known-scene rows processed: `{known_total['total']}`; filtered candidates: `{known_total['filtered']}` (`{format_value(known_total['filtered_ratio'])}`).",
            "- Unknown replay data is suitable for tool regression and before/after output checks, not for wall/box scene claims.",
            "- Known-scene data from M6 is suitable for wall/static-box before/after comparison.",
            "- Real scene labels are still required before claiming precision/recall or model-grade anomaly detection.",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "py -3 .\\tools\\m9_rule_filter.py --all",
            "py -3 .\\tools\\selfcheck_m9_rule_filter.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def analyze_dataset_group(dataset_root: Path, output_root: Path, config: RuleConfig) -> list[dict[str, Any]]:
    entries = []
    for csv_path in discover_dataset_csvs(dataset_root):
        entries.append(analyze_file(csv_path, output_root / csv_path.stem, config))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M9 rule-based point filter.")
    parser.add_argument("--input", type=Path, help="Single M8 CSV path.")
    parser.add_argument("--output-dir", type=Path, help="Output directory for single input.")
    parser.add_argument("--all", action="store_true", help="Process all M8 replay datasets.")
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--known-scene-root", type=Path, default=DEFAULT_KNOWN_SCENE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    config = RuleConfig()
    if args.all:
        replay_output_root = args.output_root / "replay_sets"
        known_output_root = args.output_root / "known_scenes"
        replay_entries = analyze_dataset_group(args.replay_root, replay_output_root, config)
        known_entries = analyze_dataset_group(args.known_scene_root, known_output_root, config)
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "README.md").write_text(render_index(replay_entries, known_entries), encoding="utf-8")
        print(f"processed {len(replay_entries)} unknown replay datasets under {replay_output_root}")
        print(f"processed {len(known_entries)} known-scene datasets under {known_output_root}")
        return 0

    if not args.input:
        parser.error("--input is required unless --all is used")
    output_dir = args.output_dir or (args.output_root / args.input.stem)
    entry = analyze_file(args.input, output_dir, config)
    print(f"wrote {entry['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
