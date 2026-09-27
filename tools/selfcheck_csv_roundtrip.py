import csv
import math
import sys
import tempfile
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_equal(actual, expected, context):
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def assert_close(actual, expected, tolerance, context):
    actual_f = float(actual)
    expected_f = float(expected)
    if not (math.isfinite(actual_f) and math.isfinite(expected_f)):
        fail(f"{context}: non-finite value, expected {expected!r}, got {actual!r}")
    if abs(actual_f - expected_f) > tolerance:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def install_gui_can_mocks():
    can_module = types.ModuleType("can")
    pg_module = types.ModuleType("pyqtgraph")
    pyside_module = types.ModuleType("PySide6")
    qtcore_module = types.ModuleType("PySide6.QtCore")
    qtgui_module = types.ModuleType("PySide6.QtGui")
    qtwidgets_module = types.ModuleType("PySide6.QtWidgets")

    class DummyWidget:
        def __init__(self, *args, **kwargs):
            pass

    qtwidgets_module.QWidget = DummyWidget
    pyside_module.QtCore = qtcore_module
    pyside_module.QtGui = qtgui_module
    pyside_module.QtWidgets = qtwidgets_module

    sys.modules.setdefault("can", can_module)
    sys.modules.setdefault("pyqtgraph", pg_module)
    sys.modules.setdefault("PySide6", pyside_module)
    sys.modules.setdefault("PySide6.QtCore", qtcore_module)
    sys.modules.setdefault("PySide6.QtGui", qtgui_module)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets_module)


def load_can_recv4():
    install_gui_can_mocks()
    import importlib

    return importlib.import_module("can_recv4")


def expected_xy(distance_cm, angle_deg):
    radius_mm = float(distance_cm) * 10.0
    theta_rad = math.radians(float(angle_deg))
    return radius_mm * math.cos(theta_rad), radius_mm * math.sin(theta_rad)


def make_points(module):
    points = []
    for index, angle in enumerate((0.0, 90.0, 180.0, 270.0)):
        points.append(
            module.LidarPoint.from_measurement(
                host_rx_time_us=1_000_000 + index * 10_000,
                t_sample_us=2_000_000 + index * 10_000,
                angle_tick=100 + index,
                angle_deg=angle,
                distance_cm=10,
                quality=200 + index,
                status=8,
                seq=index,
            )
        )
    return points


def main():
    module = load_can_recv4()
    points = make_points(module)

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "roundtrip.csv"
        writer = module.CsvPointWriter(csv_path)
        try:
            for point in points:
                writer.write_point(point)
            writer.write_summary(
                {
                    "ok": len(points),
                    "timeout": 0,
                    "overwrite_a": 0,
                    "overwrite_b": 0,
                    "pending": 0,
                }
            )
        finally:
            writer.close()

        with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            assert_equal(reader.fieldnames, module.FORMAL_CSV_FIELDS, "formal CSV header")
            if "seq" in (reader.fieldnames or []):
                fail("formal CSV unexpectedly contains seq field")
            rows = list(reader)
            assert_equal(len(rows), len(points), "CSV data row count")
            assert_equal(len(reader.fieldnames or []), 9, "formal CSV column count")

        replay = module.CsvReplaySource(csv_path)
        assert_equal(len(replay.points), len(points), "replay point count")
        assert_equal(replay.summary_stats.get("reassembly_ok_point_cnt"), str(len(points)), "summary ok count")

        for index, (expected, actual) in enumerate(zip(points, replay.points)):
            context = f"point {index}"
            assert_equal(actual.host_rx_time_us, expected.host_rx_time_us, f"{context} host_rx_time_us")
            assert_equal(actual.t_sample_us, expected.t_sample_us, f"{context} t_sample_us")
            assert_equal(actual.angle_tick, expected.angle_tick, f"{context} angle_tick")
            assert_equal(actual.distance_cm, expected.distance_cm, f"{context} distance_cm")
            assert_equal(actual.quality, expected.quality, f"{context} quality")
            assert_equal(actual.status, expected.status, f"{context} status")
            assert_close(actual.angle_deg, expected.angle_deg, 1e-6, f"{context} angle_deg")
            expected_x, expected_y = expected_xy(expected.distance_cm, expected.angle_deg)
            assert_close(actual.x_mm, expected_x, 0.01, f"{context} x_mm")
            assert_close(actual.y_mm, expected_y, 0.01, f"{context} y_mm")

    print("PASS: selfcheck_csv_roundtrip")


if __name__ == "__main__":
    main()
