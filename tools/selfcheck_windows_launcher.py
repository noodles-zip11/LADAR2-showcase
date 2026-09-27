"""Windows launcher self-check.

This does not start the Qt event loop. It only verifies that the launcher builds
a Windows-safe replay command by default and an explicit virtual live command
when requested.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_true(cond, context):
    if not cond:
        fail(f"{context}: expected True")


def assert_equal(actual, expected, context):
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def main():
    from can_recv4_windows import DEFAULT_REPLAY_CSV, build_can_recv4_args

    print("selfcheck_windows_launcher - Windows replay launcher")
    print()

    args = build_can_recv4_args()
    assert_true(DEFAULT_REPLAY_CSV.exists(), "default replay CSV exists")
    assert_true("--mode" in args, "mode option present")
    assert_equal(args[args.index("--mode") + 1], "replay", "default mode is replay")
    assert_true("--input-csv" in args, "input CSV option present")
    assert_true(str(DEFAULT_REPLAY_CSV) in args, "default CSV is used")
    assert_true("--no-mqtt" in args, "MQTT disabled by default")

    mqtt_args = build_can_recv4_args(mqtt=True, mqtt_host="127.0.0.1", mqtt_port=1883)
    assert_true("--no-mqtt" not in mqtt_args, "MQTT flag enables MQTT")
    assert_equal(mqtt_args[mqtt_args.index("--mqtt-host") + 1], "127.0.0.1", "MQTT host")

    live_args = build_can_recv4_args(
        mode="live",
        can_interface="virtual",
        channel="ladar2_virtual",
        mqtt=True,
    )
    assert_equal(live_args[live_args.index("--mode") + 1], "live", "live mode is selected")
    assert_equal(
        live_args[live_args.index("--can-interface") + 1],
        "virtual",
        "live backend is virtual",
    )
    assert_equal(
        live_args[live_args.index("--channel") + 1],
        "ladar2_virtual",
        "live channel is passed",
    )
    assert_true("--no-mqtt" not in live_args, "live MQTT flag enables MQTT")

    pcan_args = build_can_recv4_args(
        mode="live",
        can_interface="pcan",
        channel="PCAN_USBBUS1",
        bitrate=500000,
    )
    assert_equal(pcan_args[pcan_args.index("--bitrate") + 1], "500000", "bitrate is passed")

    print("[PASS] Windows launcher defaults to replay and can build explicit live CAN commands")
    print()
    print("PASS: selfcheck_windows_launcher")


if __name__ == "__main__":
    main()
