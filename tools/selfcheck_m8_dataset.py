#!/usr/bin/env python3
"""Self-check the M8 offline dataset tooling and generated bundle."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "tools" / "m8_offline_analysis.py"
DATASET_ROOT = REPO_ROOT / "docs" / "m8" / "datasets" / "replay_sets"
KNOWN_SCENE_ROOT = REPO_ROOT / "docs" / "m8" / "datasets" / "known_scenes"
SAMPLE_CSV = REPO_ROOT / "docs" / "m8" / "samples" / "sample_static_wall.csv"
SAMPLE_LABELS = REPO_ROOT / "docs" / "m8" / "samples" / "sample_static_wall.labels.csv"


def load_analysis_module():
    spec = importlib.util.spec_from_file_location("m8_offline_analysis", ANALYSIS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {ANALYSIS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_label_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def main() -> int:
    analysis = load_analysis_module()

    points, fieldnames = analysis.load_points(SAMPLE_CSV)
    metrics = analysis.compute_metrics(points)
    labels = analysis.load_labels(SAMPLE_LABELS)

    assert_true("host_rx_time_us" in fieldnames, "sample has host_rx_time_us")
    assert_true(metrics["valid_points"] == 12, "sample valid point count")
    assert_true(metrics["status_alert_count"] == 1, "sample status alert count")
    assert_true(metrics["estimated_flag_count"] == 0, "sample estimated flag count")
    estimated_only = analysis.compute_metrics([
        {
            "row": 2,
            "valid": 1,
            "host_rx_time_us": 0,
            "angle_deg": 0,
            "distance_cm": 100,
            "quality": 255,
            "status": 0x08,
        }
    ])
    assert_true(estimated_only["status_alert_count"] == 0, "status=0x08 is not an alert")
    assert_true(estimated_only["estimated_flag_count"] == 1, "status=0x08 estimated count")
    assert_true(labels["wall"] == 2, "sample wall labels")
    assert_true(labels["suspect_anomaly"] == 1, "sample anomaly label")

    index = DATASET_ROOT / "README.md"
    assert_true(index.exists(), "M8 replay index exists")
    dataset_dirs = [path for path in DATASET_ROOT.iterdir() if path.is_dir()]
    assert_true(len(dataset_dirs) >= 1, "at least one replay dataset exists")

    for dataset_dir in dataset_dirs:
        name = dataset_dir.name
        csv_path = dataset_dir / f"{name}.csv"
        labels_path = dataset_dir / f"{name}.labels.csv"
        report_path = dataset_dir / f"{name}.analysis.md"
        readme_path = dataset_dir / "README.md"
        assert_true(csv_path.exists(), f"{name}: csv exists")
        assert_true(labels_path.exists(), f"{name}: labels exists")
        assert_true(report_path.exists(), f"{name}: report exists")
        assert_true(readme_path.exists(), f"{name}: README exists")
        assert_true(len(read_label_rows(labels_path)) >= 1, f"{name}: labels template has one row")
        labels = read_label_rows(labels_path)
        assert_true(labels[0]["label"] == "unlabeled", f"{name}: unknown replay stays unlabeled")

    known_index = KNOWN_SCENE_ROOT / "README.md"
    assert_true(known_index.exists(), "M8 known-scene index exists")
    known_dirs = [path for path in KNOWN_SCENE_ROOT.iterdir() if path.is_dir()]
    assert_true(len(known_dirs) >= 6, "M8 known scenes include M6 wall and box repeats")

    expected_known_labels = {
        "m6_box_far_01": "static_box",
        "m6_box_far_02": "static_box",
        "m6_box_far_03": "static_box",
        "m6_wall_01": "wall",
        "m6_wall_02": "wall",
        "m6_wall_03": "wall",
    }
    for name, expected_label in expected_known_labels.items():
        dataset_dir = KNOWN_SCENE_ROOT / name
        csv_path = dataset_dir / f"{name}.csv"
        labels_path = dataset_dir / f"{name}.labels.csv"
        report_path = dataset_dir / f"{name}.analysis.md"
        readme_path = dataset_dir / "README.md"
        assert_true(csv_path.exists(), f"{name}: known-scene csv exists")
        assert_true(labels_path.exists(), f"{name}: known-scene labels exists")
        assert_true(report_path.exists(), f"{name}: known-scene report exists")
        assert_true(readme_path.exists(), f"{name}: known-scene README exists")
        labels = read_label_rows(labels_path)
        assert_true(len(labels) == 1, f"{name}: known-scene has one full-range label")
        assert_true(labels[0]["label"] == expected_label, f"{name}: expected known label")

    print("PASS: selfcheck_m8_dataset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
