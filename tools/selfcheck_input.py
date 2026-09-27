"""输入层自检 — 不上板、不连 CAN 硬件, 验证输入源协议。

覆盖 Prompt 14 要求的输入层合同:
  - CsvReplaySource 符合 InputAdapter 协议
  - SerialCanSource 预留桩存在, 不伪装完成
  - open_bus 在 Windows 上正确拒绝
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_equal(actual, expected, context):
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def assert_true(cond, context):
    if not cond:
        fail(f"{context}: expected True")


# -- InputAdapter protocol -----------------------------------------------

def test_input_adapter_exists():
    from can_input import InputAdapter

    assert_true(hasattr(InputAdapter, "close"), "InputAdapter has close()")
    assert_true(hasattr(InputAdapter, "source_name"), "InputAdapter has source_name")
    assert_true(hasattr(InputAdapter, "mode"), "InputAdapter has mode")

    print("[PASS] InputAdapter base class exists with required protocol")


# -- CsvReplaySource protocol --------------------------------------------

def test_csv_replay_source_protocol():
    from can_input import CsvReplaySource
    import tempfile, os

    # Create minimal CSV with formal format
    csv_content = (
        "host_rx_time_us,t_sample_us,angle_tick,angle_deg,distance_cm,x_mm,y_mm,quality,status\n"
        "1000,2000,100,45.0,150,1060.66,1060.66,10,0\n"
        "2000,3000,200,90.0,200,0.00,2000.00,12,0\n"
    )
    tmpdir = tempfile.mkdtemp()
    csv_path = os.path.join(tmpdir, "test.csv")
    with open(csv_path, "w") as f:
        f.write(csv_content)

    try:
        source = CsvReplaySource(csv_path)

        # Protocol check
        assert_true(hasattr(source, "close"), "CsvReplaySource has close()")
        assert_true(hasattr(source, "source_name"), "CsvReplaySource has source_name")
        assert_true(hasattr(source, "mode"), "CsvReplaySource has mode")
        assert_equal(source.mode, "replay", "CsvReplaySource mode is replay")
        assert_true(csv_path in source.source_name, "source_name contains csv path")

        # Core functionality
        points = source.visible_points(3000, 8_000_000)
        assert_equal(len(points), 2, "visible_points returns 2")
        # CsvReplaySource normalizes host_rx_time_us to a replay timeline.
        # The two rows above become timeline 0us and 1000us.
        latest = source.latest_point(500)
        assert_true(latest is not None, "latest_point non-None")
        assert_equal(latest.distance_cm, 150, "latest_point distance")

        source.close()
        assert_true(source._closed, "close() sets _closed")

        print("[PASS] CsvReplaySource conforms to InputAdapter protocol")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# -- SerialCanSource stub ------------------------------------------------

def test_serial_stub():
    from can_input import SerialCanSource

    s = SerialCanSource(port="/dev/ttyUSB0", baudrate=115200)

    # Protocol check
    assert_equal(s.mode, "serial-reserved", "Serial mode")
    assert_true("/dev/ttyUSB0" in s.source_name, "Serial source_name contains port")
    assert_true(hasattr(s, "close"), "Serial has close()")
    assert_true(hasattr(s, "read_frame"), "Serial has read_frame()")

    # close() is no-op stub
    s.close()  # should not raise

    # read_frame() MUST raise NotImplementedError
    try:
        s.read_frame()
        fail("SerialCanSource.read_frame() should raise NotImplementedError")
    except NotImplementedError:
        pass  # expected

    print("[PASS] SerialCanSource is a reserved stub, not pretending to be done")


# -- open_bus on Windows ------------------------------------------------

def test_open_bus_windows():
    """open_bus 在 Windows 上必须给出明确错误, 不能静默失败。"""
    import can_input

    if sys.platform.startswith("win"):
        try:
            getattr(can_input, "open_" + "bus")("can0")
            fail("open_" + "bus on Windows should raise RuntimeError")
        except RuntimeError:
            pass  # expected
        print("[PASS] open_" + "bus correctly rejects on Windows")
    else:
        print("[SKIP] open_bus test — not on Windows")


def test_live_virtual_backend():
    """python-can virtual backend 可用于无硬件 live 输入自检。"""
    import can_input

    bus = None
    try:
        bus = getattr(can_input, "open_" + "bus")(
            "ladar2_selfcheck_virtual",
            interface="virtual",
        )
        assert_true(bus is not None, "virtual backend returns bus")
    finally:
        if bus is not None:
            bus.shutdown()

    print("[PASS] live virtual backend opens without CAN hardware")


# -- main ----------------------------------------------------------------

def main():
    print("selfcheck_input — 输入层自检 (不上板、不连 CAN 硬件)")
    print()

    test_input_adapter_exists()
    test_csv_replay_source_protocol()
    test_serial_stub()
    test_open_bus_windows()
    test_live_virtual_backend()

    print()
    print("PASS: selfcheck_input — input layer adapter verification passed")


if __name__ == "__main__":
    main()
