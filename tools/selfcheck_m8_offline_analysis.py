#!/usr/bin/env python3
"""M8 离线分析脚本自检。

这个自检不上板、不连 CAN、不依赖 GUI，只用临时 CSV 验证
tools/m8_offline_analysis.py 的核心合同是否稳定。
"""

from __future__ import annotations

import math
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


def assert_close(actual: float, expected: float, tolerance: float, context: str) -> None:
    if math.fabs(actual - expected) > tolerance:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def assert_true(condition: bool, context: str) -> None:
    if not condition:
        fail(f"{context}: expected True")


def write_sample_csv(path: Path) -> None:
    # 同时放入正常点、无效行、负距离和非零 status，覆盖统计里的边界分支。
    path.write_text(
        "\n".join(
            [
                "host_rx_time_us,angle_deg,distance_cm,quality,status",
                "0,370,100,20,0",
                "1000000,-10,50,5,8",
                "bad,20,30,10,0",
                "2000000,45,-1,15,3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_labels_csv(path: Path) -> None:
    # 标签文件只检查 M8 骨架当前需要的三列，避免提前绑定后续标注格式。
    path.write_text(
        "\n".join(
            [
                "start_host_rx_time_us,end_host_rx_time_us,label",
                "0,1000000,wall",
                "1000000,2000000,wall",
                "2000000,3000000,box",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def check_numeric_parsing(module) -> None:
    assert_equal(module.parse_float({"v": ""}, "v"), None, "blank parses as None")
    assert_equal(module.parse_float({"v": "not-a-number"}, "v"), None, "invalid parses as None")
    assert_equal(module.parse_float({"v": "inf"}, "v"), None, "non-finite parses as None")
    assert_close(module.parse_float({"v": "12.5"}, "v"), 12.5, 0.0, "valid float parsing")
    print("[PASS] M8 parse_float handles blank/invalid/non-finite values")


def check_load_metrics_and_labels(module, tmpdir: Path) -> tuple[Path, Path, dict[str, object]]:
    csv_path = tmpdir / "m8_sample.csv"
    labels_path = tmpdir / "m8_labels.csv"
    write_sample_csv(csv_path)
    write_labels_csv(labels_path)

    points, fieldnames = module.load_points(csv_path)
    labels = module.load_labels(labels_path)
    metrics = module.compute_metrics(points)

    assert_equal(fieldnames, ["host_rx_time_us", "angle_deg", "distance_cm", "quality", "status"], "CSV fields")
    assert_equal(len(points), 4, "total loaded rows")
    assert_equal(sum(1 for point in points if point.get("valid") == 1), 3, "valid point count")
    assert_equal(points[0]["angle_deg"], 10.0, "angle normalization above 360")
    assert_equal(points[1]["angle_deg"], 350.0, "angle normalization below 0")

    assert_equal(labels["wall"], 2, "label count wall")
    assert_equal(labels["box"], 1, "label count box")
    assert_equal(metrics["total_rows"], 4, "metrics total rows")
    assert_equal(metrics["valid_points"], 3, "metrics valid points")
    assert_equal(metrics["invalid_rows"], 1, "metrics invalid rows")
    assert_close(metrics["duration_s"], 2.0, 0.000001, "metrics duration")
    assert_close(metrics["estimated_rate_hz"], 1.0, 0.000001, "metrics rate")
    assert_equal(metrics["distance_cm_min"], -1.0, "metrics distance min")
    assert_equal(metrics["status_distribution"], {0: 1, 3: 1, 8: 1}, "metrics status distribution")

    print("[PASS] M8 load_points/load_labels/compute_metrics cover valid and invalid rows")
    return csv_path, labels_path, metrics


def check_missing_required_fields(module, tmpdir: Path) -> None:
    bad_csv = tmpdir / "bad.csv"
    bad_csv.write_text("host_rx_time_us,angle_deg\n0,90\n", encoding="utf-8")
    try:
        module.load_points(bad_csv)
    except ValueError as exc:
        assert_true("distance_cm" in str(exc), "missing distance field reported")
    else:
        fail("load_points should reject CSV missing distance_cm")

    bad_labels = tmpdir / "bad_labels.csv"
    bad_labels.write_text("start_host_rx_time_us,label\n0,wall\n", encoding="utf-8")
    try:
        module.load_labels(bad_labels)
    except ValueError as exc:
        assert_true("end_host_rx_time_us" in str(exc), "missing label field reported")
    else:
        fail("load_labels should reject labels missing end_host_rx_time_us")

    print("[PASS] M8 rejects CSV/label files with missing required fields")


def check_markdown_and_cli(module, tmpdir: Path, csv_path: Path, labels_path: Path) -> None:
    output_path = tmpdir / "report.md"
    old_argv = sys.argv[:]
    try:
        # 直接调用 main，确认命令行入口会写出 Markdown 报告。
        sys.argv = [
            "m8_offline_analysis.py",
            "--input",
            str(csv_path),
            "--labels",
            str(labels_path),
            "--output",
            str(output_path),
        ]
        assert_equal(module.main(), 0, "M8 CLI return code")
    finally:
        sys.argv = old_argv

    report = output_path.read_text(encoding="utf-8")
    assert_true("# M8 离线分析报告" in report, "report title")
    assert_true("| `valid_points` | 3 |" in report, "report valid_points metric")
    assert_true("| `wall` | 2 |" in report, "report label distribution")
    print("[PASS] M8 CLI writes Markdown report with metrics and labels")


def main() -> None:
    import m8_offline_analysis as module

    print("selfcheck_m8_offline_analysis - M8 离线分析自检")
    print()
    with tempfile.TemporaryDirectory(prefix="m8_selfcheck_") as tmp:
        tmpdir = Path(tmp)
        check_numeric_parsing(module)
        csv_path, labels_path, _metrics = check_load_metrics_and_labels(module, tmpdir)
        check_missing_required_fields(module, tmpdir)
        check_markdown_and_cli(module, tmpdir, csv_path, labels_path)

    print()
    print("PASS: selfcheck_m8_offline_analysis")


if __name__ == "__main__":
    main()
