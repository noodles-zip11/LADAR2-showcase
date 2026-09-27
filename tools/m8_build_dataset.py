#!/usr/bin/env python3
"""Build the M8 offline dataset bundle from existing CSV captures."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Any

import m8_offline_analysis as analysis


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = REPO_ROOT / "docs" / "m8" / "datasets"
KNOWN_SCENE_SOURCES = [
    {
        "name": "m6_box_far_01",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "repeat_far_01.csv",
        "label": "static_box",
        "comment": "M6 known scene: far static box repeat 01",
        "category": "known_scenes",
    },
    {
        "name": "m6_box_far_02",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "repeat_far_02.csv",
        "label": "static_box",
        "comment": "M6 known scene: far static box repeat 02",
        "category": "known_scenes",
    },
    {
        "name": "m6_box_far_03",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "repeat_far_03.csv",
        "label": "static_box",
        "comment": "M6 known scene: far static box repeat 03",
        "category": "known_scenes",
    },
    {
        "name": "m6_wall_01",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "wall_01.csv",
        "label": "wall",
        "comment": "M6 known scene: static wall repeat 01",
        "category": "known_scenes",
    },
    {
        "name": "m6_wall_02",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "wall_02.csv",
        "label": "wall",
        "comment": "M6 known scene: static wall repeat 02",
        "category": "known_scenes",
    },
    {
        "name": "m6_wall_03",
        "source": REPO_ROOT / "docs" / "m6" / "runs" / "m6_manual" / "data" / "wall_03.csv",
        "label": "wall",
        "comment": "M6 known scene: static wall repeat 03",
        "category": "known_scenes",
    },
]


def read_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def labels_time_range(points: list[dict[str, float | int | None]]) -> tuple[int | None, int | None]:
    times = [int(float(p["host_rx_time_us"])) for p in points if p.get("valid") == 1]
    if not times:
        return None, None
    return min(times), max(times)


def write_label_template(
    path: Path,
    start_us: int | None,
    end_us: int | None,
    *,
    label: str = "unlabeled",
    comment: str = "scene label needs manual confirmation",
) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["start_host_rx_time_us", "end_host_rx_time_us", "label", "comment"])
        if start_us is not None and end_us is not None:
            writer.writerow([start_us, end_us, label, comment])


def format_value(value: object) -> str:
    return analysis.format_value(value)


def render_dataset_readme(
    *,
    dataset_name: str,
    source_path: Path,
    csv_path: Path,
    labels_path: Path,
    report_path: Path,
    metrics: dict[str, Any],
    summary: dict[str, str],
    scene_label: str,
    category: str,
    label_comment: str,
) -> str:
    rows = [
        "# M8 数据集条目",
        "",
        "## 1. 基本信息",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 数据集名称 | `{dataset_name}` |",
        f"| 来源 CSV | `{source_path}` |",
        f"| 场景标签 | `{scene_label}` |",
        f"| 标签说明 | {label_comment} |",
        f"| 分类 | `{category}` |",
        "",
        "## 2. 文件清单",
        "",
        "| 文件 | 说明 |",
        "| --- | --- |",
        f"| `{csv_path.name}` | 原始 CSV 副本 |",
        f"| `{labels_path.name}` | 标签模板 |",
        f"| `{report_path.name}` | 离线分析报告 |",
        "",
        "## 3. 分析摘要",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
    ]
    for key in (
        "total_rows",
        "valid_points",
        "duration_s",
        "estimated_rate_hz",
        "distance_cm_median",
        "distance_cm_p95",
        "status_distribution",
        "status_alert_count",
        "estimated_flag_ratio",
        "near_obstacle_count",
        "too_near_count",
        "angle_coverage_ratio",
        "outline_spread_cm_median",
    ):
        rows.append(f"| `{key}` | {format_value(metrics.get(key))} |")

    rows.extend(["", "## 4. 采集摘要"])
    if summary:
        rows.extend(["", "| 字段 | 值 |", "| --- | --- |"])
        for key, value in summary.items():
            rows.append(f"| `{key}` | `{value}` |")
    else:
        rows.append("")
        rows.append("未找到同名 `_summary.txt`。")

    rows.extend([
        "",
        "## 5. 标签状态",
        "",
        f"当前标签为 `{scene_label}`。未知场景保持 `unlabeled`；只有 M6 这类来源明确的数据才写入具体场景标签。",
        "",
    ])
    return "\n".join(rows)


def render_replay_index(entries: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> str:
    lines = [
        "# M8 数据集索引",
        "",
        "本目录由 `tools/m8_build_dataset.py` 从根目录已有 `can_distance_*.csv` 构建。",
        "",
        "这些采集只证明数据可回放、可统计、可进入离线分析；由于缺少现场记录，不承担墙面、箱子、拐角或动态目标等场景语义。",
        "",
        "## 可回放数据集",
        "",
        "| 数据集 | 点数 | 时长 s | 点率 Hz | 状态分布 | 标签状态 |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for entry in entries:
        metrics = entry["metrics"]
        lines.append(
            f"| [{entry['name']}]({entry['name']}/README.md) "
            f"| {format_value(metrics.get('valid_points'))} "
            f"| {format_value(metrics.get('duration_s'))} "
            f"| {format_value(metrics.get('estimated_rate_hz'))} "
            f"| `{metrics.get('status_distribution')}` "
            f"| `unlabeled` |"
        )

    lines.extend([
        "",
        "## 未纳入回放集的采集",
        "",
        "| 文件 | 原因 |",
        "| --- | --- |",
    ])
    if skipped:
        for item in skipped:
            lines.append(f"| `{item['path'].name}` | {item['reason']} |")
    else:
        lines.append("| n/a | 无 |")

    lines.extend([
        "",
        "## 使用方式",
        "",
        "单文件分析：",
        "",
        "```powershell",
        "py -3 .\\tools\\m8_offline_analysis.py --input .\\docs\\m8\\datasets\\replay_sets\\<dataset>\\<dataset>.csv --labels .\\docs\\m8\\datasets\\replay_sets\\<dataset>\\<dataset>.labels.csv",
        "```",
        "",
        "重建数据集：",
        "",
        "```powershell",
        "py -3 .\\tools\\m8_build_dataset.py",
        "```",
        "",
        "## 边界",
        "",
        "- 本索引不把 `unlabeled` 当作真实场景标签。",
        "- 不知道现场的 5 月 7 日和 5 月 9/10 日根目录采集，只能保留为 unknown replay 数据。",
        "- `status=0x08` 按 estimated 标记统计，不按异常统计。",
        "- 后续若补充采集现场记录，可以只编辑对应 `.labels.csv` 和条目 README。",
    ])
    return "\n".join(lines) + "\n"


def render_known_scene_index(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# M8 已知场景数据集索引",
        "",
        "本目录由 `tools/m8_build_dataset.py` 从 M6 几何质量数据构建。",
        "这些 CSV 的场景来源在 M6 中已经明确，因此可以带真实场景标签。",
        "",
        "## 已知场景数据集",
        "",
        "| 数据集 | 来源 | 点数 | 时长 s | 点率 Hz | 标签 |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for entry in entries:
        metrics = entry["metrics"]
        lines.append(
            f"| [{entry['name']}]({entry['name']}/README.md) "
            f"| `{entry['source'].relative_to(REPO_ROOT)}` "
            f"| {format_value(metrics.get('valid_points'))} "
            f"| {format_value(metrics.get('duration_s'))} "
            f"| {format_value(metrics.get('estimated_rate_hz'))} "
            f"| `{entry['label']}` |"
        )

    lines.extend([
        "",
        "## 标签口径",
        "",
        "- `static_box`：M6 远距静态箱体重复采样，用于轮廓重复性和四边质量观察。",
        "- `wall`：M6 静态墙面重复采样，用于直线度和重复偏移观察。",
        "- 不从未知 replay 数据反推场景标签。",
    ])
    return "\n".join(lines) + "\n"


def build_dataset_entry(
    *,
    dataset_dir: Path,
    dataset_name: str,
    source_path: Path,
    label: str,
    label_comment: str,
    category: str,
    overwrite_labels: bool,
) -> dict[str, Any]:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dataset_dir / f"{dataset_name}.csv"
    labels_path = dataset_dir / f"{dataset_name}.labels.csv"
    report_path = dataset_dir / f"{dataset_name}.analysis.md"
    readme_path = dataset_dir / "README.md"

    points, fieldnames = analysis.load_points(source_path)
    metrics = analysis.compute_metrics(points)
    shutil.copy2(source_path, csv_path)
    start_us, end_us = labels_time_range(points)
    if overwrite_labels or not labels_path.exists():
        write_label_template(labels_path, start_us, end_us, label=label, comment=label_comment)

    labels = analysis.load_labels(labels_path)
    report_path.write_text(
        analysis.render_markdown(csv_path, fieldnames, metrics, labels),
        encoding="utf-8",
    )

    summary_path = source_path.with_name(f"{source_path.stem}_summary.txt")
    readme_path.write_text(
        render_dataset_readme(
            dataset_name=dataset_name,
            source_path=source_path,
            csv_path=csv_path,
            labels_path=labels_path,
            report_path=report_path,
            metrics=metrics,
            summary=read_summary(summary_path),
            scene_label=label,
            category=category,
            label_comment=label_comment,
        ),
        encoding="utf-8",
    )

    return {
        "name": dataset_name,
        "source": source_path,
        "label": label,
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build M8 replay dataset bundle.")
    parser.add_argument("--source-glob", default="can_distance_*.csv")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--min-points", type=int, default=1)
    parser.add_argument(
        "--overwrite-labels",
        action="store_true",
        help="Rewrite existing labels CSV files. Defaults to preserving manual labels.",
    )
    args = parser.parse_args()

    replay_root = args.dataset_root / "replay_sets"
    known_root = args.dataset_root / "known_scenes"
    replay_root.mkdir(parents=True, exist_ok=True)
    known_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    known_entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for source_path in sorted(REPO_ROOT.glob(args.source_glob)):
        points, fieldnames = analysis.load_points(source_path)
        metrics = analysis.compute_metrics(points)
        if int(metrics["valid_points"]) < args.min_points:
            skipped.append({"path": source_path, "reason": "no valid points"})
            continue

        dataset_name = source_path.stem
        dataset_dir = replay_root / dataset_name
        entries.append(
            build_dataset_entry(
                dataset_dir=dataset_dir,
                dataset_name=dataset_name,
                source_path=source_path,
                label="unlabeled",
                label_comment="unknown replay capture; scene is not claimed",
                category="replay_sets",
                overwrite_labels=args.overwrite_labels,
            )
        )

    for source in KNOWN_SCENE_SOURCES:
        source_path = Path(source["source"])
        if not source_path.exists():
            skipped.append({"path": source_path, "reason": "known scene source missing"})
            continue
        points, _fieldnames = analysis.load_points(source_path)
        metrics = analysis.compute_metrics(points)
        if int(metrics["valid_points"]) < args.min_points:
            skipped.append({"path": source_path, "reason": "no valid points"})
            continue

        dataset_name = str(source["name"])
        known_entries.append(
            build_dataset_entry(
                dataset_dir=known_root / dataset_name,
                dataset_name=dataset_name,
                source_path=source_path,
                label=str(source["label"]),
                label_comment=str(source["comment"]),
                category=str(source["category"]),
                overwrite_labels=args.overwrite_labels,
            )
        )

    index_path = replay_root / "README.md"
    index_path.write_text(render_replay_index(entries, skipped), encoding="utf-8")
    known_index_path = known_root / "README.md"
    known_index_path.write_text(render_known_scene_index(known_entries), encoding="utf-8")
    print(f"built {len(entries)} dataset entries under {replay_root}")
    print(f"built {len(known_entries)} known-scene entries under {known_root}")
    if skipped:
        print(f"skipped {len(skipped)} empty/invalid captures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
