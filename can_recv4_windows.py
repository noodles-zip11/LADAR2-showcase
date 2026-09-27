"""Windows-friendly launcher for the 2D LiDAR UI.

By default this launcher starts the same application in replay mode with a
bundled sample CSV. It can also start live mode on Windows when a python-can
backend is selected explicitly. For no-hardware testing use the ``virtual``
backend; real adapters still require the vendor driver and python-can support.
"""

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_REPLAY_CSV = REPO_ROOT / "docs" / "m4" / "data" / "can_distance_v2_sample.csv"


def build_can_recv4_args(
    *,
    mode="replay",
    input_csv=None,
    replay_speed="1",
    can_interface="virtual",
    channel="ladar2_virtual",
    bitrate=None,
    mqtt=False,
    mqtt_host="localhost",
    mqtt_port=1883,
):
    """Build argv for can_recv4.py on Windows."""
    args = ["--mode", str(mode)]
    if mode == "replay":
        csv_path = Path(input_csv).resolve() if input_csv else DEFAULT_REPLAY_CSV
        args.extend(
            [
                "--input-csv",
                str(csv_path),
                "--replay-speed",
                str(replay_speed),
            ]
        )
    elif mode == "live":
        args.extend(
            [
                "--channel",
                str(channel),
                "--can-interface",
                str(can_interface),
            ]
        )
        if bitrate is not None:
            args.extend(["--bitrate", str(bitrate)])
    else:
        raise ValueError(f"unsupported mode: {mode}")

    args.extend(["--mqtt-host", str(mqtt_host), "--mqtt-port", str(mqtt_port)])
    if not mqtt:
        args.append("--no-mqtt")
    return args


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Windows launcher for can_recv4.py")
    parser.add_argument(
        "--mode",
        choices=("replay", "live"),
        default="replay",
        help="Default is replay. Use live only with a selected python-can backend.",
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=DEFAULT_REPLAY_CSV,
        help="CSV file to replay. Defaults to docs/m4/data/can_distance_v2_sample.csv",
    )
    parser.add_argument(
        "--replay-speed",
        choices=("0.5", "1", "2"),
        default="1",
        help="Replay speed multiplier.",
    )
    parser.add_argument(
        "--can-interface",
        default="virtual",
        help="python-can backend for Windows live mode, for example virtual, pcan, kvaser, vector, slcan.",
    )
    parser.add_argument(
        "--channel",
        default="ladar2_virtual",
        help="CAN channel for live mode. Examples: ladar2_virtual, PCAN_USBBUS1, COM3.",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        default=None,
        help="CAN bitrate for live mode when required by the backend, for example 500000.",
    )
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="Enable MQTT output. By default Windows replay runs without MQTT.",
    )
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the equivalent can_recv4.py arguments and exit.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    can_recv4_args = build_can_recv4_args(
        mode=args.mode,
        input_csv=args.input_csv,
        replay_speed=args.replay_speed,
        can_interface=args.can_interface,
        channel=args.channel,
        bitrate=args.bitrate,
        mqtt=args.mqtt,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
    )

    if args.print_command:
        print("python can_recv4.py " + " ".join(can_recv4_args))
        return 0

    if args.mode == "replay" and not Path(args.input_csv).exists():
        print(f"Replay CSV not found: {args.input_csv}")
        return 1

    from can_recv4 import main as can_recv4_main

    return can_recv4_main(can_recv4_args)


if __name__ == "__main__":
    raise SystemExit(main())
