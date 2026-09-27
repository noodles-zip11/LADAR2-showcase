#!/usr/bin/env python3
"""Selfcheck for the M9 rule-based point quality filter."""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_equal(actual, expected, context: str) -> None:
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def assert_true(condition: bool, context: str) -> None:
    if not condition:
        fail(f"{context}: expected True")


def write_sample(path: Path) -> None:
    rows = [
        ["host_rx_time_us", "angle_deg", "distance_cm", "quality", "status"],
        [0, 0, 100, 255, 0],
        [1000, 1, 101, 255, 0],
        [2000, 2, 260, 255, 0],
        [3000, 3, 102, 255, 0],
        [4000, 4, 103, 5, 0],
        [5000, 5, 104, 255, 3],
        [6000, 6, -1, 255, 0],
        ["bad", 7, 100, 255, 0],
        [7000, 8, 105, 255, 8],
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def main() -> None:
    import m9_rule_filter as module

    print("selfcheck_m9_rule_filter - M9 rule filter selfcheck")
    print()

    with tempfile.TemporaryDirectory(prefix="m9_selfcheck_") as tmp:
        tmpdir = Path(tmp)
        input_path = tmpdir / "sample.csv"
        output_dir = tmpdir / "out"
        write_sample(input_path)

        rows, fieldnames = module.load_rows(input_path)
        results = module.classify_rows(rows, module.RuleConfig(stability_min_bin_points=50))
        summary = module.summarize(rows, results)

        assert_equal(fieldnames, ["host_rx_time_us", "angle_deg", "distance_cm", "quality", "status"], "fieldnames")
        assert_equal(summary["total_rows"], 9, "total rows")
        assert_equal(summary["valid_inputs"], 8, "valid inputs")
        assert_true(summary["filtered_points"] >= 5, "multiple rule violations are filtered")

        reasons = "\n".join(result["m9_reasons"] for result in results)
        for reason in (
            "distance_jump",
            "low_quality",
            "status_alert",
            "nonpositive_distance",
            "invalid_input",
        ):
            assert_true(reason in reasons, f"{reason} is reported")

        entry = module.analyze_file(input_path, output_dir, module.RuleConfig(stability_min_bin_points=50))
        assert_true(entry["filtered_csv"].exists(), "filtered CSV exists")
        assert_true(entry["report"].exists(), "report exists")

        filtered_text = entry["filtered_csv"].read_text(encoding="utf-8")
        assert_true("m9_keep,m9_reasons" in filtered_text.splitlines()[0], "M9 columns are appended")
        report_text = entry["report"].read_text(encoding="utf-8")
        assert_true("M9 Rule Quality Gate Appendix Report" in report_text, "report title")

        replay_root = tmpdir / "m8" / "replay_sets"
        known_root = tmpdir / "m8" / "known_scenes"
        replay_dataset = replay_root / "unknown_capture"
        known_dataset = known_root / "m6_wall_01"
        replay_dataset.mkdir(parents=True)
        known_dataset.mkdir(parents=True)
        replay_csv = replay_dataset / "unknown_capture.csv"
        known_csv = known_dataset / "m6_wall_01.csv"
        write_sample(replay_csv)
        write_sample(known_csv)

        all_output = tmpdir / "m9_all"
        replay_entries = module.analyze_dataset_group(
            replay_root,
            all_output / "replay_sets",
            module.RuleConfig(stability_min_bin_points=50),
        )
        known_entries = module.analyze_dataset_group(
            known_root,
            all_output / "known_scenes",
            module.RuleConfig(stability_min_bin_points=50),
        )
        index_text = module.render_index(replay_entries, known_entries)
        (all_output / "README.md").write_text(index_text, encoding="utf-8")
        assert_equal(len(replay_entries), 1, "one replay entry")
        assert_equal(len(known_entries), 1, "one known-scene entry")
        assert_true((all_output / "replay_sets" / "unknown_capture" / "unknown_capture.m9_report.md").exists(), "replay report path")
        assert_true((all_output / "known_scenes" / "m6_wall_01" / "m6_wall_01.m9_report.md").exists(), "known-scene report path")
        assert_true("Unknown Replay Results" in index_text, "index has replay section")
        assert_true("Known Scene Results" in index_text, "index has known-scene section")

    print("[PASS] M9 rule filter flags distance, continuity, status, quality, and invalid-input cases")
    print()
    print("PASS: selfcheck_m9_rule_filter")


if __name__ == "__main__":
    main()
