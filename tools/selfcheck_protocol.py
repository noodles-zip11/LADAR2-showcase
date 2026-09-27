import math
import struct
import sys
import time
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


def make_msg(arbitration_id, data):
    return types.SimpleNamespace(arbitration_id=arbitration_id, data=bytes(data))


def header_msg(module, seq, distance_cm, angle_deg, quality):
    angle_bytes = struct.pack(">f", float(angle_deg))
    data = bytes([seq & 0xFF]) + int(distance_cm).to_bytes(2, "big") + angle_bytes + bytes([quality & 0xFF])
    return make_msg(module.FRAME_HEADER_ID, data)


def tail_msg(module, seq, t_sample_us, angle_tick, status):
    data = (
        bytes([seq & 0xFF])
        + int(t_sample_us).to_bytes(4, "big")
        + int(angle_tick).to_bytes(2, "big")
        + bytes([status & 0xFF])
    )
    return make_msg(module.FRAME_TAIL_ID, data)


def expected_xy(distance_cm, angle_deg):
    radius_mm = float(distance_cm) * 10.0
    theta_rad = math.radians(float(angle_deg))
    return radius_mm * math.cos(theta_rad), radius_mm * math.sin(theta_rad)


def assert_point(point, *, seq, distance_cm, angle_deg, quality, t_sample_us, angle_tick, status, context):
    assert_equal(point.seq, seq, f"{context} seq")
    assert_equal(point.distance_cm, distance_cm, f"{context} distance_cm")
    assert_close(point.angle_deg, angle_deg, 1e-5, f"{context} angle_deg")
    assert_equal(point.quality, quality, f"{context} quality")
    assert_equal(point.t_sample_us, t_sample_us, f"{context} t_sample_us")
    assert_equal(point.angle_tick, angle_tick, f"{context} angle_tick")
    assert_equal(point.status, status, f"{context} status")
    expected_x, expected_y = expected_xy(distance_cm, angle_deg)
    assert_close(point.x_mm, expected_x, 1e-4, f"{context} x_mm")
    assert_close(point.y_mm, expected_y, 1e-4, f"{context} y_mm")


def test_ordered_pair(module):
    assembler = module.CanPointAssembler()
    out = assembler.process_message(header_msg(module, 7, 123, 45.5, 200))
    assert_equal(out, [], "ordered header alone")
    out = assembler.process_message(tail_msg(module, 7, 0x01020304, 0x1234, 8))
    assert_equal(len(out), 1, "ordered pair output count")
    assert_point(out[0], seq=7, distance_cm=123, angle_deg=45.5, quality=200, t_sample_us=0x01020304, angle_tick=0x1234, status=8, context="ordered pair")
    assert_equal(assembler.stats_snapshot()["ok"], 1, "ordered pair ok count")


def test_reordered_pair(module):
    assembler = module.CanPointAssembler()
    out = assembler.process_message(tail_msg(module, 8, 7654321, 321, 3))
    assert_equal(out, [], "reordered tail alone")
    out = assembler.process_message(header_msg(module, 8, 77, 270.25, 111))
    assert_equal(len(out), 1, "reordered pair output count")
    assert_point(out[0], seq=8, distance_cm=77, angle_deg=270.25, quality=111, t_sample_us=7654321, angle_tick=321, status=3, context="reordered pair")


def test_seq_wraparound(module):
    assembler = module.CanPointAssembler()
    for index, seq in enumerate((254, 255, 0, 1)):
        out = assembler.process_message(header_msg(module, seq, 50 + index, index * 10.0, 10 + index))
        assert_equal(out, [], f"wrap header seq {seq}")
        out = assembler.process_message(tail_msg(module, seq, 1000 + index, 200 + index, index))
        assert_equal(len(out), 1, f"wrap output seq {seq}")
        assert_equal(out[0].seq, seq, f"wrap point seq {seq}")
    assert_equal(assembler.stats_snapshot()["ok"], 4, "wrap ok count")


def test_timeout_without_sleep(module):
    assembler = module.CanPointAssembler(timeout_s=0.050)
    seq = 42
    assembler.process_message(header_msg(module, seq, 10, 0.0, 1))
    frame = assembler.pending_frames.get(seq)
    if frame is None:
        fail("timeout setup missing pending frame")
    frame["first_rx_monotonic"] = time.monotonic() - assembler.timeout_s - 1.0
    assembler.prune_stale_frames()
    stats = assembler.stats_snapshot()
    assert_equal(stats["timeout"], 1, "timeout count")
    assert_equal(stats["pending"], 0, "timeout pending count")


def test_overwrite_header(module):
    assembler = module.CanPointAssembler()
    seq = 9
    assembler.process_message(header_msg(module, seq, 10, 1.0, 1))
    assembler.process_message(header_msg(module, seq, 20, 2.0, 2))
    out = assembler.process_message(tail_msg(module, seq, 99, 88, 7))
    assert_equal(len(out), 1, "header overwrite output count")
    assert_equal(assembler.stats_snapshot()["overwrite_a"], 1, "header overwrite count")
    assert_point(out[0], seq=seq, distance_cm=20, angle_deg=2.0, quality=2, t_sample_us=99, angle_tick=88, status=7, context="header overwrite")


def test_overwrite_tail(module):
    assembler = module.CanPointAssembler()
    seq = 10
    assembler.process_message(tail_msg(module, seq, 111, 222, 1))
    assembler.process_message(tail_msg(module, seq, 333, 444, 2))
    out = assembler.process_message(header_msg(module, seq, 66, 12.5, 55))
    assert_equal(len(out), 1, "tail overwrite output count")
    assert_equal(assembler.stats_snapshot()["overwrite_b"], 1, "tail overwrite count")
    assert_point(out[0], seq=seq, distance_cm=66, angle_deg=12.5, quality=55, t_sample_us=333, angle_tick=444, status=2, context="tail overwrite")


def test_bad_id_and_short_dlc(module):
    unknown_id_assembler = module.CanPointAssembler()
    out = unknown_id_assembler.process_message(make_msg(0x999, bytes([1, 2, 3, 4, 5, 6, 7, 8])))
    assert_equal(out, [], "bad CAN ID output")
    unknown_stats = unknown_id_assembler.stats_snapshot()
    assert_equal(unknown_stats["ok"], 0, "bad CAN ID ok count")
    assert_equal(unknown_stats["pending"], 0, "bad CAN ID pending count")

    short_dlc_assembler = module.CanPointAssembler()
    out = short_dlc_assembler.process_message(make_msg(module.FRAME_HEADER_ID, bytes([1, 2, 3])))
    assert_equal(out, [], "short DLC output")
    short_stats = short_dlc_assembler.stats_snapshot()
    assert_equal(short_stats["ok"], 0, "short DLC ok count")
    assert_equal(short_stats["pending"], 0, "short DLC pending count")


def main():
    module = load_can_recv4()
    assert_equal(module.FRAME_HEADER_ID, 0x123, "FRAME_HEADER_ID")
    assert_equal(module.FRAME_TAIL_ID, 0x124, "FRAME_TAIL_ID")

    test_ordered_pair(module)
    test_reordered_pair(module)
    test_seq_wraparound(module)
    test_timeout_without_sleep(module)
    test_overwrite_header(module)
    test_overwrite_tail(module)
    test_bad_id_and_short_dlc(module)

    print("PASS: selfcheck_protocol")


if __name__ == "__main__":
    main()
