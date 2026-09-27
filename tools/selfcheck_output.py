"""输出层自检 — 验证 CSV / log / MQTT adapter 最小边界。"""

import contextlib
import io
import sys
import tempfile
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


class _FakePoint:
    def to_csv_row(self):
        return [1000, 2000, 123, "45.00", 100, "707.11", "707.11", 12, 0]


def test_output_adapter_base():
    from can_output import OutputAdapter

    assert_true(hasattr(OutputAdapter, "close"), "OutputAdapter has close")
    assert_true(hasattr(OutputAdapter, "adapter_name"), "OutputAdapter has adapter_name")
    print("[PASS] OutputAdapter base protocol exists")


def test_csv_adapter():
    from can_output import CsvPointWriter

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "points.csv"
        writer = CsvPointWriter(csv_path)
        try:
            assert_equal(writer.adapter_name, "csv", "CsvPointWriter adapter_name")
            writer.write_point(_FakePoint())
            writer.write_summary(
                {
                    "ok": 1,
                    "timeout": 0,
                    "overwrite_a": 0,
                    "overwrite_b": 0,
                    "pending": 0,
                }
            )
        finally:
            writer.close()

        assert_true(csv_path.exists(), "CSV file exists")
        assert_true(writer.summary_path.exists(), "summary file exists")
        assert_true("host_rx_time_us" in csv_path.read_text(encoding="utf-8"), "CSV header")

    print("[PASS] CsvPointWriter adapter writes CSV and summary")


def test_log_adapter():
    from can_output import LogOutputAdapter

    adapter = LogOutputAdapter()
    assert_equal(adapter.adapter_name, "log", "LogOutputAdapter adapter_name")
    summary = {
        "mode": "replay",
        "point_count": 2,
        "sweep_point_count": 2,
        "min_distance_cm": 50,
        "is_alert": True,
        "alert_level": 3,
        "sectors": [
            {"name": "Front", "point_count": 1, "min_distance_cm": 50, "alert_level": 3},
        ],
    }
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        adapter.emit_summary(summary)
    output = buf.getvalue()
    assert_true("[LOG]" in output, "log prefix")
    assert_true("mode=replay" in output, "log mode")
    assert_true("Front" in output, "log sector")
    adapter.close()
    print("[PASS] LogOutputAdapter emits structured summary")


def test_mqtt_adapter():
    from can_mqtt import MqttOutput

    mqtt = MqttOutput(host="localhost", port=1883, node_id="01", device_id="lidar-01")
    assert_equal(mqtt.adapter_name, "mqtt", "MqttOutput adapter_name")
    assert_true(hasattr(mqtt, "close"), "MqttOutput has close")
    assert_true(mqtt.topic_status == "lidar/01/status", "MqttOutput topic status")
    print("[PASS] MqttOutput adapter boundary exists")


def main():
    print("selfcheck_output — 输出层 adapter 自检 (不上板、不连 Broker)")
    print()
    test_output_adapter_base()
    test_csv_adapter()
    test_log_adapter()
    test_mqtt_adapter()
    print()
    print("PASS: selfcheck_output — output adapter verification passed")


if __name__ == "__main__":
    main()
