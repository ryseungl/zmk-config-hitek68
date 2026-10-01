"""Diagnostic: capture raw bytes for a get_keymap RPC.

Run:  py diag_keymap.py
Reports timing/byte counts so we can see whether the dongle sends a
partial frame, a slow trickle, or nothing at all.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen"))

from client import find_studio_port, frame, FRAME_START, FRAME_END
import serial
import studio_pb2


def raw_exchange(name, build_fn, listen_secs=12.0):
    port = find_studio_port()
    if not port:
        print("No Studio port found")
        return
    ser = serial.Serial(port, baudrate=115200, timeout=0.05)
    time.sleep(0.2)
    ser.reset_input_buffer()

    req = studio_pb2.Request(request_id=7)
    build_fn(req)
    payload = req.SerializeToString()
    print(f"[{name}] request bytes: {len(payload)}")
    ser.write(frame(payload))

    start = time.monotonic()
    data = bytearray()
    first_at = None
    last_at = None
    end_seen = False
    while time.monotonic() - start < listen_secs:
        chunk = ser.read(4096)
        if chunk:
            now = time.monotonic() - start
            if first_at is None:
                first_at = now
            last_at = now
            data.extend(chunk)
            if FRAME_END in chunk:
                # crude: stop shortly after first 0xAD following a 0xAB
                end_seen = True
                break
        elif data and time.monotonic() - last_at > 2.0:
            break  # silence for 2s after data started: give up
    total = time.monotonic() - start

    print(f"[{name}] first byte at +{first_at:.3f}s" if first_at is not None else f"[{name}] NO BYTES received")
    print(f"[{name}] total bytes: {len(data)} in {total:.2f}s")
    if data:
        print(f"[{name}] last byte at +{last_at:.3f}s; 0xAD seen: {end_seen}")
        print(f"[{name}] first 32 bytes: {data[:32].hex(' ')}")
        print(f"[{name}] starts with 0xAB: {data[0] == FRAME_START}")
    ser.close()


raw_exchange("get_device_info", lambda r: setattr(r.core, "get_device_info", True), listen_secs=6.0)
print()
raw_exchange("get_keymap", lambda r: setattr(r.keymap, "get_keymap", True), listen_secs=12.0)
