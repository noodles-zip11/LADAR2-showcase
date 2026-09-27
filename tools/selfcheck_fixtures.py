import csv
import math
import re
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "docs" / "m4" / "data"
EXPECTED_HEADER = [
    "host_rx_time_us",
    "t_sample_us",
    "angle_tick",
    "angle_deg",
    "distance_cm",
    "x_mm",
    "y_mm",
    "quality",
    "status",
]
CANDUMP_RE = re.compile(r"^\s*\S+\s+([0-9A-Fa-f]+)\s+\[(\d+)\]\s+((?:[0-9A-Fa-f]{2}\s+){7}[0-9A-Fa-f]{2})\s*$")
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


def parse_summary(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def parse_candump_frames(path):
    frames = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        match = CANDUMP_RE.match(stripped)
        if not match:
            fail(f"candump parse failed at line {line_number}: {stripped}")
        can_id = int(match.group(1), 16)
        dlc = int(match.group(2))
        if can_id not in (0x123, 0x124):
            fail(f"unexpected CAN ID 0x{can_id:X} at line {line_number}")
        assert_equal(dlc, 8, f"candump DLC line {line_number}")
        data = bytes(int(token, 16) for token in match.group(3).split())
        frames.append({"line": line_number, "can_id": can_id, "seq": data[0], "data": data})
    if not frames:
        fail(f"empty candump log: {path}")
    return frames


def check_candump_seq_pairing(path):
    frames = parse_candump_frames(path)
    pair_count = 0
    index = 0
    while index < len(frames) - 1:
        header_frame = frames[index]
        tail_frame = frames[index + 1]
        if header_frame["can_id"] == 0x123 and tail_frame["can_id"] == 0x124 and header_frame["seq"] == tail_frame["seq"]:
            pair_count += 1
            index += 2
        else:
            fail(
                f"candump seq pairing broken at line {header_frame['line']}: "
                f"expected adjacent 0x123+0x124 with same seq, "
                f"got can_id=0x{header_frame['can_id']:X} seq={header_frame['seq']} "
                f"followed by can_id=0x{tail_frame['can_id']:X} seq={tail_frame['seq']}"
            )
    if index < len(frames):
        last = frames[index]
        fail(f"candump trailing unpaired frame at line {last['line']}: can_id=0x{last['can_id']:X} seq={last['seq']}")
    return frames, pair_count


def check_candump_reassembly(module, frames, expected_pair_count):
    assembler = module.CanPointAssembler()
    assembled_points = 0
    for frame in frames:
        msg = types.SimpleNamespace(arbitration_id=frame["can_id"], data=frame["data"])
        out = assembler.process_message(msg)
        assembled_points += len(out)
    stats = assembler.stats_snapshot()
    assert_equal(assembled_points, expected_pair_count, "candump assembled point count")
    assert_equal(stats["ok"], expected_pair_count, "candump assembler ok count")
    assert_equal(stats["pending"], 0, "candump assembler pending count")


def check_csv_and_summary(module, csv_name, summary_name):
    csv_path = DATA_DIR / csv_name
    summary_path = DATA_DIR / summary_name
    if not csv_path.exists():
        fail(f"missing fixture CSV: {csv_path}")
    if not summary_path.exists():
        fail(f"missing fixture summary: {summary_path}")

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        try:
            header = next(reader)
        except StopIteration:
            fail(f"empty CSV: {csv_path}")
        assert_equal(header, EXPECTED_HEADER, f"CSV header {csv_name}")
        expected_col_count = len(EXPECTED_HEADER)
        numeric_fields = {"host_rx_time_us", "t_sample_us", "angle_tick", "angle_deg", "distance_cm", "x_mm", "y_mm", "quality", "status"}
        for row_index, row in enumerate(reader, start=2):
            if len(row) != expected_col_count:
                fail(f"{csv_name} row {row_index}: expected {expected_col_count} columns, got {len(row)}")
            for col_index, (field_name, cell) in enumerate(zip(EXPECTED_HEADER, row)):
                if field_name in numeric_fields and (cell is None or cell.strip() == ""):
                    fail(f"{csv_name} row {row_index} field {field_name}: empty numeric field")

    summary = parse_summary(summary_path)
    replay = module.CsvReplaySource(csv_path)
    row_count = len(replay.points)

    assert_equal(int(summary.get("reassembly_ok_point_cnt", "-1")), row_count, f"summary ok count {summary_name}")
    assert_equal(int(summary.get("reassembly_timeout_point_cnt", "-1")), 0, f"summary timeout count {summary_name}")
    assert_equal(int(summary.get("reassembly_overwrite_a_cnt", "-1")), 0, f"summary overwrite_a count {summary_name}")
    assert_equal(int(summary.get("reassembly_overwrite_b_cnt", "-1")), 0, f"summary overwrite_b count {summary_name}")
    assert_equal(int(summary.get("pending_frame_cnt", "-1")), 0, f"summary pending count {summary_name}")

    for index, point in enumerate(replay.points):
        context = f"{csv_name} row {index + 1}"
        if not isinstance(point.host_rx_time_us, int):
            fail(f"{context}: host_rx_time_us not parsed as int")
        if not isinstance(point.t_sample_us, int):
            fail(f"{context}: t_sample_us not parsed as int")
        if not isinstance(point.angle_tick, int):
            fail(f"{context}: angle_tick not parsed as int")
        if not isinstance(point.distance_cm, int):
            fail(f"{context}: distance_cm not parsed as int")
        if not isinstance(point.quality, int):
            fail(f"{context}: quality not parsed as int")
        if not isinstance(point.status, int):
            fail(f"{context}: status not parsed as int")
        expected_x, expected_y = module.compute_xy_mm(point.distance_cm, point.angle_deg)
        assert_close(point.x_mm, expected_x, 0.01, f"{context} x_mm geometry")
        assert_close(point.y_mm, expected_y, 0.01, f"{context} y_mm geometry")

    return row_count


def main():
    module = load_can_recv4()
    candump_path = DATA_DIR / "candump_m4_live.log"
    frames, pair_count = check_candump_seq_pairing(candump_path)
    check_candump_reassembly(module, frames, pair_count)

    check_csv_and_summary(module, "can_distance_v2_sample.csv", "can_distance_v2_sample_summary.txt")
    check_csv_and_summary(module, "can_distance_20260329_145239.csv", "can_distance_20260329_145239_summary.txt")

    print("PASS: selfcheck_fixtures")


if __name__ == "__main__":
    main()
