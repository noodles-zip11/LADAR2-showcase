"""Windows CAN probe for LADAR2 live testing.

Use this instead of ``python -m can.logger`` for candleLight/gs_usb adapters on
Windows. The project ``open_bus`` helper wires PyUSB to libusb-package, while
the generic python-can CLI does not.
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from can_input import open_bus
from can_parser import CanPointAssembler, FRAME_HEADER_ID, FRAME_TAIL_ID


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Probe Windows CAN frames for LADAR2.")
    parser.add_argument("--can-interface", default="gs_usb")
    parser.add_argument("--channel", default="0")
    parser.add_argument("--bitrate", type=int, default=500000)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--max-print", type=int, default=40)
    parser.add_argument(
        "--parse",
        action="store_true",
        help="Also run CanPointAssembler and print reconstructed points.",
    )
    return parser.parse_args(argv)


def format_data(data):
    return " ".join(f"{byte:02X}" for byte in data)


def main(argv=None):
    args = parse_args(argv)
    bus = None
    counts = Counter()
    printed = 0
    point_count = 0
    assembler = CanPointAssembler() if args.parse else None

    print(
        "OPEN "
        f"interface={args.can_interface} channel={args.channel} bitrate={args.bitrate}"
    )
    print(f"LISTEN {args.seconds:g}s")

    try:
        bus = open_bus(args.channel, interface=args.can_interface, bitrate=args.bitrate)
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                print(".", end="", flush=True)
                continue

            counts[msg.arbitration_id] += 1
            if printed < args.max_print:
                print(
                    "\nFRAME "
                    f"id=0x{msg.arbitration_id:03X} "
                    f"dlc={msg.dlc} "
                    f"data={format_data(msg.data)}",
                    flush=True,
                )
                printed += 1

            if assembler is not None:
                for point in assembler.process_message(msg):
                    point_count += 1
                    print(
                        "POINT "
                        f"seq={point.seq} "
                        f"distance_cm={point.distance_cm} "
                        f"angle_deg={point.angle_deg:.2f} "
                        f"quality={point.quality} "
                        f"status=0x{point.status:02X}",
                        flush=True,
                    )
                assembler.prune_stale_frames()
    except KeyboardInterrupt:
        print("\nSTOP: interrupted")
    finally:
        if bus is not None:
            bus.shutdown()

    print()
    total = sum(counts.values())
    print(f"TOTAL_FRAMES {total}")
    for can_id, count in sorted(counts.items()):
        print(f"ID=0x{can_id:03X} count={count}")

    if assembler is not None:
        print(f"POINTS {point_count}")
        print(f"ASSEMBLER {assembler.stats_snapshot()}")

    if counts.get(FRAME_HEADER_ID, 0) and counts.get(FRAME_TAIL_ID, 0):
        print("PASS: received expected LADAR frame IDs 0x123 and 0x124")
    elif total:
        print("WARN: CAN traffic received, but missing 0x123 or 0x124")
    else:
        print("WARN: no CAN frames received")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
