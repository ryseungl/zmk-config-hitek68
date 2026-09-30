#!/usr/bin/env python3
"""
Hitek68 runtime settings — adjust debounce and deep-sleep timeout without
reflashing.

Sends commands to the dongle via HID output reports (Report ID 0x02) on the
vendor interface (Usage Page 0xFF00). The dongle relays them to the halves
over BLE; halves apply immediately and persist to flash.

Usage:
    python hitek68_settings.py debounce --press 5 --release 5
    python hitek68_settings.py debounce --press 10 --release 10 --target left
    python hitek68_settings.py sleep --timeout 1800000
    python hitek68_settings.py sleep --timeout 0        # never sleep
    python hitek68_settings.py sleep --minutes 30

Targets: both (default), left, right
"""

import argparse
import struct
import sys

try:
    import hid
except ImportError:
    print("Missing dependency: pip install hidapi", file=sys.stderr)
    sys.exit(1)

DONGLE_VID = 0x1D50
DONGLE_PID = 0x615E
VENDOR_USAGE_PAGE = 0xFF00
VENDOR_USAGE = 0x01

REPORT_ID_COMMAND = 0x02
CMD_SET_DEBOUNCE = 0x01
CMD_SET_SLEEP = 0x02

TARGETS = {"both": 0, "left": 1, "right": 2}

DEBOUNCE_MAX_MS = 16383
SLEEP_MIN_MS = 60000  # 1 minute (0 = disabled)


def find_device():
    for dev in hid.enumerate(DONGLE_VID, DONGLE_PID):
        if (dev.get("usage_page") == VENDOR_USAGE_PAGE
                and dev.get("usage") == VENDOR_USAGE):
            return dev["path"]
    return None


def send_command(cmd, target, payload):
    """Send an output report: [0x02, cmd, target, payload(5 bytes)]."""
    path = find_device()
    if not path:
        print("Dongle not found. Is it plugged in with the new firmware?",
              file=sys.stderr)
        sys.exit(1)

    report = bytes([REPORT_ID_COMMAND, cmd, target]) + payload
    # Pad/truncate to 8 bytes total (ID + 7 data bytes)
    report = report[:8].ljust(8, b"\x00")

    try:
        with hid.device() as h:
            h.open_path(path)
            n = h.write(report)
    except OSError as e:
        print(f"Failed to send command: {e}", file=sys.stderr)
        sys.exit(1)

    if n != len(report):
        print(f"Warning: only wrote {n}/{len(report)} bytes", file=sys.stderr)


def cmd_debounce(args):
    if not (0 <= args.press <= DEBOUNCE_MAX_MS):
        print(f"press must be 0-{DEBOUNCE_MAX_MS} ms", file=sys.stderr)
        sys.exit(1)
    if not (0 <= args.release <= DEBOUNCE_MAX_MS):
        print(f"release must be 0-{DEBOUNCE_MAX_MS} ms", file=sys.stderr)
        sys.exit(1)

    target = TARGETS[args.target]
    payload = struct.pack("<HH", args.press, args.release) + b"\x00"
    send_command(CMD_SET_DEBOUNCE, target, payload)
    print(f"Debounce -> {args.target}: press={args.press}ms release={args.release}ms")


def cmd_sleep(args):
    if args.minutes is not None:
        timeout_ms = int(args.minutes * 60000)
    else:
        timeout_ms = args.timeout

    if timeout_ms != 0 and timeout_ms < SLEEP_MIN_MS:
        print(f"timeout must be 0 (never) or >= {SLEEP_MIN_MS}ms (1 min)",
              file=sys.stderr)
        sys.exit(1)

    target = TARGETS[args.target]
    payload = struct.pack("<I", timeout_ms) + b"\x00"
    send_command(CMD_SET_SLEEP, target, payload)

    if timeout_ms == 0:
        desc = "never"
    else:
        desc = f"{timeout_ms}ms ({timeout_ms/60000:.1f} min)"
    print(f"Sleep timeout -> {args.target}: {desc}")


def main():
    p = argparse.ArgumentParser(description="Hitek68 runtime settings (no reflash)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("debounce", help="Set key debounce times")
    d.add_argument("--press", type=int, default=5, help="Press debounce ms (0-16383)")
    d.add_argument("--release", type=int, default=5, help="Release debounce ms (0-16383)")
    d.add_argument("--target", choices=TARGETS, default="both")
    d.set_defaults(func=cmd_debounce)

    s = sub.add_parser("sleep", help="Set deep-sleep idle timeout")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--timeout", type=int, help="Timeout in ms (0 = never sleep)")
    g.add_argument("--minutes", type=float, help="Timeout in minutes")
    s.add_argument("--target", choices=TARGETS, default="both")
    s.set_defaults(func=cmd_sleep)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
