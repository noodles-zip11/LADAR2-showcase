import math
import sys
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


def assert_is_nan(value, context):
    if not math.isnan(value):
        fail(f"{context}: expected NaN, got {value!r}")


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


def make_point(module, *, angle_deg, distance_cm=10, angle_tick=0, host_rx_time_us=0, t_sample_us=0):
    return module.LidarPoint.from_measurement(
        host_rx_time_us=host_rx_time_us,
        t_sample_us=t_sample_us,
        angle_tick=angle_tick,
        angle_deg=angle_deg,
        distance_cm=distance_cm,
        quality=255,
        status=8,
        seq=None,
    )


def test_compute_xy_mm(module):
    x, y = module.compute_xy_mm(10, 0)
    assert_close(x, 100.0, 1e-6, "xy 0deg x")
    assert_close(y, 0.0, 1e-6, "xy 0deg y")

    x, y = module.compute_xy_mm(10, 90)
    assert_close(x, 0.0, 1e-6, "xy 90deg x")
    assert_close(y, 100.0, 1e-6, "xy 90deg y")

    x, y = module.compute_xy_mm(10, 180)
    assert_close(x, -100.0, 1e-6, "xy 180deg x")
    assert_close(y, 0.0, 1e-6, "xy 180deg y")

    x, y = module.compute_xy_mm(10, 270)
    assert_close(x, 0.0, 1e-6, "xy 270deg x")
    assert_close(y, -100.0, 1e-6, "xy 270deg y")

    expected = 100.0 / math.sqrt(2.0)
    x, y = module.compute_xy_mm(10, 45)
    assert_close(x, expected, 1e-6, "xy 45deg x")
    assert_close(y, expected, 1e-6, "xy 45deg y")

    x, y = module.compute_xy_mm(0, 123)
    assert_close(x, 0.0, 1e-6, "xy zero distance x")
    assert_close(y, 0.0, 1e-6, "xy zero distance y")


def test_angular_delta_deg(module):
    assert_close(module.angular_delta_deg(10, 5), 5.0, 1e-9, "delta simple positive")
    assert_close(module.angular_delta_deg(5, 10), -5.0, 1e-9, "delta simple negative")
    assert_close(module.angular_delta_deg(359, 1), -2.0, 1e-9, "delta wrap 359 1")
    assert_close(module.angular_delta_deg(1, 359), 2.0, 1e-9, "delta wrap 1 359")
    assert_close(module.angular_delta_deg(0, 360), 0.0, 1e-9, "delta 0 360")
    assert_close(module.angular_delta_deg(180, 0), -180.0, 1e-9, "delta 180 0")
    assert_close(module.angular_delta_deg(0, 180), -180.0, 1e-9, "delta 0 180")


def test_extract_recent_sweep(module):
    points = [make_point(module, angle_deg=float(angle), angle_tick=index, host_rx_time_us=index, t_sample_us=index) for index, angle in enumerate(range(0, 360, 10))]
    sweep = module.extract_recent_sweep(points, target_travel_deg=340.0)
    if len(sweep) < module.MIN_SWEEP_POINT_COUNT:
        fail(f"extract_recent_sweep returned too few points: {len(sweep)}")
    assert_equal(sweep[-1].angle_deg, points[-1].angle_deg, "recent sweep last point")

    one = [make_point(module, angle_deg=15.0)]
    sweep = module.extract_recent_sweep(one)
    assert_equal(len(sweep), 1, "single point sweep length")
    assert_close(sweep[0].angle_deg, 15.0, 1e-9, "single point sweep value")

    short_points = [make_point(module, angle_deg=float(angle)) for angle in (0, 20, 40, 60)]
    sweep = module.extract_recent_sweep(short_points, target_travel_deg=300.0)
    assert_equal(len(sweep), len(short_points), "short sweep returns all points")


def test_build_sweep_curve(module):
    near_points = [
        make_point(module, angle_deg=0.0, distance_cm=10),
        make_point(module, angle_deg=5.0, distance_cm=10),
    ]
    xs, ys = module.build_sweep_curve(near_points, break_distance_mm=120.0)
    assert_equal(len(xs), 2, "near curve length x")
    assert_equal(len(ys), 2, "near curve length y")

    far_points = [
        make_point(module, angle_deg=0.0, distance_cm=10),
        make_point(module, angle_deg=180.0, distance_cm=10),
    ]
    xs, ys = module.build_sweep_curve(far_points, break_distance_mm=120.0)
    assert_equal(len(xs), 3, "far curve length x")
    assert_equal(len(ys), 3, "far curve length y")
    assert_is_nan(xs[1], "far curve NaN x")
    assert_is_nan(ys[1], "far curve NaN y")

    xs, ys = module.build_sweep_curve([])
    assert_equal(xs, [], "empty curve xs")
    assert_equal(ys, [], "empty curve ys")

    single = [make_point(module, angle_deg=30.0, distance_cm=10)]
    xs, ys = module.build_sweep_curve(single)
    assert_equal(len(xs), 1, "single curve xs length")
    assert_equal(len(ys), 1, "single curve ys length")
    assert_close(xs[0], single[0].x_mm, 1e-6, "single curve x value")
    assert_close(ys[0], single[0].y_mm, 1e-6, "single curve y value")


def main():
    module = load_can_recv4()
    test_compute_xy_mm(module)
    test_angular_delta_deg(module)
    test_extract_recent_sweep(module)
    test_build_sweep_curve(module)
    print("PASS: selfcheck_geometry")


if __name__ == "__main__":
    main()
