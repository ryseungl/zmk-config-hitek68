#!/usr/bin/env python3
"""
Hitek68 battery monitor — reads per-half battery levels from the dongle's
vendor USB HID interface and displays them in the terminal.

The dongle firmware (config/src/battery_hid.c) exposes a vendor-defined HID
interface (Usage Page 0xFF00) that sends 3-byte input reports:
    byte 0: report ID (0x01)
    byte 1: left half state of charge (0-100, 0xFF = unknown)
    byte 2: right half state of charge (0-100, 0xFF = unknown)

Cross-platform: uses hidapi, works on Windows/macOS/Linux.
Requires: pip install hidapi

Usage:
    python hitek68_battery.py          # live dashboard
    python hitek68_battery.py --once   # print once and exit
"""

import argparse
import sys
import time

try:
    import hid
except ImportError:
    print("Missing dependency: pip install hidapi", file=sys.stderr)
    sys.exit(1)

# ZMK default USB VID:PID (Hitek68 does not override these)
DONGLE_VID = 0x1D50
DONGLE_PID = 0x615E

# Our vendor interface: Usage Page 0xFF00, Usage 0x01.
# This distinguishes it from the keyboard interface (same VID:PID).
VENDOR_USAGE_PAGE = 0xFF00
VENDOR_USAGE = 0x01

REPORT_ID = 0x01
UNKNOWN = 0xFF
REPORT_LEN = 3


def find_battery_device():
    """Return the hid device path for our vendor battery interface, or None."""
    for dev in hid.enumerate(DONGLE_VID, DONGLE_PID):
        if (dev.get("usage_page") == VENDOR_USAGE_PAGE
                and dev.get("usage") == VENDOR_USAGE):
            return dev["path"]
    return None


def fmt_level(v):
    if v is None or v == UNKNOWN:
        return "  ?  "
    return f"{v:3d}%"


def bar(v, width=20):
    if v is None or v == UNKNOWN:
        return "[" + "?" * width + "]"
    filled = int(round(v / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def read_report(h, timeout_ms=5000):
    """Read one input report, return (left, right) or (None, None) on timeout."""
    data = h.read(REPORT_LEN, timeout_ms=timeout_ms)
    if not data or len(data) < REPORT_LEN:
        return None, None
    rid, left, right = data[0], data[1], data[2]
    if rid != REPORT_ID:
        return None, None
    return left, right


def show(left, right, connected):
    status = "connected" if connected else "dongle not found"
    print(f"\rHitek68 [{status}]  "
          f"L {bar(left)} {fmt_level(left)}   "
          f"R {bar(right)} {fmt_level(right)}   ", end="", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Hitek68 battery monitor")
    ap.add_argument("--once", action="store_true",
                    help="print one reading and exit")
    args = ap.parse_args()

    left = right = None

    def poll_once():
        nonlocal left, right
        path = find_battery_device()
        if path is None:
            return False
        try:
            h = hid.device()
            h.open_path(path)
            h.set_nonblocking(False)
            l, r = read_report(h)
            h.close()
            if l is not None:
                left, right = l, r
            return True
        except (OSError, IOError):
            return False

    if args.once:
        ok = poll_once()
        if ok:
            print(f"left={fmt_level(left).strip()} right={fmt_level(right).strip()}")
        else:
            print("dongle not found", file=sys.stderr)
            sys.exit(1)
        return

    print("Hitek68 battery monitor — Ctrl+C to quit")
    try:
        while True:
            ok = poll_once()
            show(left, right, ok)
            # Firmware resends every 3s; poll a bit faster to catch changes.
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        # Clean up the current line
        print()


if __name__ == "__main__":
    main()
