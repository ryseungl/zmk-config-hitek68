"""ZMK Studio RPC Python client for the Hitek68 keybind editor.

Talks to the dongle's Studio RPC interface over USB CDC-ACM serial using
the framing from the Studio RPC protocol:

    start 0xAB | payload (with 0xAB/0xAC/0xAD escaped via 0xAC prefix) | end 0xAD

Usage::

    from client import Studio

    with Studio() as s:                      # auto-detects the dongle
        print(s.get_lock_state())            # 1 == unlocked
        km = s.get_keymap()
        for layer in km.layers:
            print(layer.id, layer.name, len(layer.bindings))
        s.set_binding(layer_id=0, position=5, behavior_id=kp_id, param1=keycode("A"))
        if s.check_unsaved_changes():
            s.save_changes()

Behavior IDs come from ``list_behaviors()`` / ``get_behavior_details()``.
For ``&kp``-style bindings, ``param1`` is the 32-bit keycode (see keycodes.py).
"""

import collections
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen"))

import serial
import serial.tools.list_ports

import studio_pb2
import core_pb2
import keymap_pb2
import behaviors_pb2
import meta_pb2

# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

FRAME_START = 0xAB
FRAME_END = 0xAD
FRAME_ESC = 0xAC

_ESCAPED = (FRAME_START, FRAME_ESC, FRAME_END)

# VID:PID of the Hitek68 dongle's USB serial (Studio RPC / CDC-ACM).
STUDIO_VID = 0x1D50
STUDIO_PID = 0x615E

# Sanity cap on a single decoded frame payload.
MAX_FRAME_SIZE = 64 * 1024

DEFAULT_TIMEOUT = 3.0


def frame(payload: bytes) -> bytes:
    """Wrap ``payload`` in a Studio RPC frame.

    Prepends 0xAB, appends 0xAD, and escapes every 0xAB/0xAC/0xAD byte in
    the payload with a 0xAC prefix.
    """
    out = bytearray()
    out.append(FRAME_START)
    for b in payload:
        if b in _ESCAPED:
            out.append(FRAME_ESC)
        out.append(b)
    out.append(FRAME_END)
    return bytes(out)


def _read_byte(ser, deadline, what):
    """Read one byte, raising TimeoutError past the deadline."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("timed out %s" % what)
    old_timeout = ser.timeout
    try:
        ser.timeout = remaining
        data = ser.read(1)
    finally:
        ser.timeout = old_timeout
    if not data:
        raise TimeoutError("timed out %s" % what)
    return data[0]


def read_frame(ser, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """Read one framed payload from ``ser``.

    Skips bytes until an unescaped 0xAB start marker, accumulates until an
    unescaped 0xAD end marker, un-escapes 0xAC-prefixed bytes, and resyncs
    (restarts) on an unescaped 0xAB seen mid-frame. Raises TimeoutError if
    no complete frame arrives within ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout

    # Wait for the start marker.
    while True:
        if _read_byte(ser, deadline, "waiting for frame start") == FRAME_START:
            break

    buf = bytearray()
    while True:
        b = _read_byte(ser, deadline, "waiting for frame data")
        if b == FRAME_END:
            return bytes(buf)
        if b == FRAME_ESC:
            buf.append(_read_byte(ser, deadline, "reading escaped byte"))
        elif b == FRAME_START:
            buf.clear()  # resync: a new frame started mid-stream
        else:
            buf.append(b)
        if len(buf) > MAX_FRAME_SIZE:
            raise ValueError("frame exceeds %d bytes" % MAX_FRAME_SIZE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def crc16_arc(data: bytes) -> int:
    """CRC-16/ARC (poly 0xA001 reflected, init 0x0000, xorout 0x0000).

    Used for ZMK Studio behavior ID calculation.
    """
    crc = 0x0000
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _probe_studio(ser, timeout: float = 1.0) -> bool:
    """Return True if ``ser`` answers a core.get_device_info RPC."""
    req = studio_pb2.Request(request_id=1)
    req.core.get_device_info = True
    ser.write(frame(req.SerializeToString()))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            payload = read_frame(ser, timeout=max(0.1, deadline - time.monotonic()))
        except (TimeoutError, ValueError):
            return False
        try:
            resp = studio_pb2.Response()
            resp.ParseFromString(payload)
        except Exception:
            continue
        if resp.WhichOneof("type") == "request_response":
            return True
    return False


def find_studio_port(timeout: float = 1.0):
    """Return the serial port path of the Studio RPC device, or None.

    Scans serial ports matching VID:PID 1D50:615E and returns the first one
    that answers a ``core.get_device_info`` RPC.
    """
    for port in serial.tools.list_ports.comports():
        if port.vid != STUDIO_VID or port.pid != STUDIO_PID:
            continue
        ser = None
        try:
            ser = serial.Serial(port.device, baudrate=115200, timeout=timeout)
            if _probe_studio(ser, timeout=timeout):
                return port.device
        except (serial.SerialException, OSError):
            continue
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
    return None


class StudioError(Exception):
    """Raised when the device reports an RPC error or a call fails."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class Studio:
    """ZMK Studio RPC client.

    ``port`` may be a serial device path; if None, the dongle is
    auto-detected via :func:`find_studio_port`.
    """

    def __init__(self, port=None, timeout: float = DEFAULT_TIMEOUT):
        if port is None:
            port = find_studio_port()
        if port is None:
            raise StudioError(
                "no Studio RPC device found (looked for USB VID:PID %04X:%04X)"
                % (STUDIO_VID, STUDIO_PID)
            )
        self.port = port
        self.timeout = timeout
        self.ser = serial.Serial(port, baudrate=115200, timeout=timeout)
        self._request_id = 0
        self._notifications = collections.deque()

    # -- context manager ----------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    # -- core RPC plumbing --------------------------------------------------
    def rpc(self, build_fn, timeout: float = None):
        """Send one RPC and return its ``RequestResponse``.

        ``build_fn`` receives a ``studio_pb2.Request`` (with ``request_id``
        already set) and fills in the subsystem request, e.g.::

            s.rpc(lambda r: setattr(r.keymap, "get_keymap", True))

        Frames arriving out of band are parsed; notifications are stashed
        in the notification queue (see :meth:`get_notifications`) and the
        loop continues until a ``request_response`` with the matching
        ``request_id`` arrives. Raises :class:`StudioError` on device-side
        RPC errors and :class:`TimeoutError` when nothing arrives in time.
        """
        self._request_id = (self._request_id + 1) & 0xFFFFFFFF
        if self._request_id == 0:
            self._request_id = 1
        req = studio_pb2.Request(request_id=self._request_id)
        build_fn(req)
        self.ser.write(frame(req.SerializeToString()))

        wait = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + wait
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "no response to request %d within %.1fs"
                    % (self._request_id, wait)
                )
            try:
                payload = read_frame(self.ser, timeout=remaining)
            except ValueError:
                continue  # oversized/garbage frame; keep waiting
            resp = studio_pb2.Response()
            try:
                resp.ParseFromString(payload)
            except Exception:
                continue  # not a valid Response; keep waiting
            if resp.WhichOneof("type") == "notification":
                self._notifications.append(resp.notification)
                continue
            if resp.WhichOneof("type") != "request_response":
                continue
            rr = resp.request_response
            if rr.request_id != self._request_id:
                continue  # stale response from an earlier request
            if rr.WhichOneof("subsystem") == "meta":
                meta = rr.meta
                if meta.WhichOneof("response_type") == "simple_error":
                    name = meta_pb2.ErrorConditions.Name(meta.simple_error)
                    raise StudioError("device RPC error: %s" % name)
            return rr

    # -- core ---------------------------------------------------------------
    def get_lock_state(self):
        """Return the Studio lock state (0 = locked, 1 = unlocked)."""
        rr = self.rpc(lambda r: setattr(r.core, "get_lock_state", True))
        return rr.core.get_lock_state

    def get_device_info(self):
        """Return the GetDeviceInfoResponse (name, serial_number)."""
        rr = self.rpc(lambda r: setattr(r.core, "get_device_info", True))
        return rr.core.get_device_info

    # -- keymap --------------------------------------------------------------
    def get_keymap(self):
        """Return the full Keymap message (layers, 96 bindings each)."""
        rr = self.rpc(lambda r: setattr(r.keymap, "get_keymap", True))
        return rr.keymap.get_keymap

    def set_binding(self, layer_id, position, behavior_id, param1=0, param2=0):
        """Set one key binding. Returns True on success."""

        def build(r):
            r.keymap.set_layer_binding.layer_id = layer_id
            r.keymap.set_layer_binding.key_position = position
            b = r.keymap.set_layer_binding.binding
            b.behavior_id = behavior_id
            b.param1 = param1
            b.param2 = param2

        rr = self.rpc(build)
        return (
            rr.keymap.set_layer_binding
            == keymap_pb2.SET_LAYER_BINDING_RESP_OK
        )

    def check_unsaved_changes(self):
        """Return True if there are unsaved keymap changes."""
        rr = self.rpc(lambda r: setattr(r.keymap, "check_unsaved_changes", True))
        return bool(rr.keymap.check_unsaved_changes)

    def save_changes(self):
        """Persist pending keymap changes to flash. Returns True on success."""
        rr = self.rpc(lambda r: setattr(r.keymap, "save_changes", True))
        res = rr.keymap.save_changes
        return res.WhichOneof("result") == "ok" and bool(res.ok)

    def discard_changes(self):
        """Discard pending keymap changes. Returns True on success."""
        rr = self.rpc(lambda r: setattr(r.keymap, "discard_changes", True))
        return bool(rr.keymap.discard_changes)

    # -- behaviors ------------------------------------------------------------
    def list_behaviors(self):
        """Return a list of behavior IDs known to the device."""
        rr = self.rpc(lambda r: setattr(r.behaviors, "list_all_behaviors", True))
        return list(rr.behaviors.list_all_behaviors.behaviors)

    def get_behavior_details(self, behavior_id):
        """Return GetBehaviorDetailsResponse (id, display_name, metadata)."""
        rr = self.rpc(
            lambda r: setattr(
                r.behaviors.get_behavior_details, "behavior_id", behavior_id
            )
        )
        return rr.behaviors.get_behavior_details

    # -- notifications ----------------------------------------------------------
    def get_notifications(self):
        """Return and clear the queue of pending notifications."""
        notes = list(self._notifications)
        self._notifications.clear()
        return notes


def _decode_frame(wire: bytes) -> bytes:
    """Decode one frame from an in-memory buffer (test helper)."""
    assert wire[0] == FRAME_START and wire[-1] == FRAME_END
    out = bytearray()
    it = iter(wire[1:-1])
    for b in it:
        if b == FRAME_ESC:
            out.append(next(it))
        else:
            out.append(b)
    return bytes(out)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import random

    print("== framing roundtrip ==")
    # loop:// echoes everything we write back to us.
    ser = serial.serial_for_url("loop://", timeout=1.0)

    random.seed(42)
    for i in range(200):
        length = random.randint(0, 64)
        payload = bytes(random.randint(0, 255) for _ in range(length))
        # Bias toward the special bytes so escapes get exercised.
        payload = bytes(
            random.choice([0xAB, 0xAC, 0xAD, b]) for b in payload
        )
        ser.write(frame(payload))
        got = read_frame(ser, timeout=2.0)
        assert got == payload, "roundtrip mismatch on iter %d" % i
    print("200 random roundtrips OK (incl. 0xAB/0xAC/0xAD-heavy payloads)")

    print("== resync ==")
    # Garbage, then an unescaped 0xAB mid-frame must restart the frame.
    ser.write(b"\x00\xffgarbage")
    ser.write(frame(b"first"))
    bad = frame(b"second")
    # Corrupt it: inject a raw 0xAB in the middle of the escaped payload,
    # then terminate with a proper end marker.
    ser.write(bad[:4] + b"\xAB" + b"second" + bytes([FRAME_END]))
    got = read_frame(ser, timeout=2.0)
    assert got == b"first", "expected 'first', got %r" % got
    got = read_frame(ser, timeout=2.0)
    assert got == b"second", "expected resync to 'second', got %r" % got
    print("garbage skip + mid-frame resync OK")

    print("== timeout ==")
    try:
        read_frame(ser, timeout=0.2)
        raise AssertionError("expected TimeoutError")
    except TimeoutError:
        print("TimeoutError raised as expected")

    print("== crc16_arc ==")
    # CRC-16/ARC check value for the ASCII string "123456789" is 0xBB3D.
    assert crc16_arc(b"123456789") == 0xBB3D, hex(crc16_arc(b"123456789"))
    print("crc16_arc('123456789') = 0xBB3D OK")

    print("== proto smoke ==")
    req = studio_pb2.Request(request_id=7)
    req.keymap.set_layer_binding.layer_id = 0
    req.keymap.set_layer_binding.key_position = 5
    req.keymap.set_layer_binding.binding.behavior_id = 1
    req.keymap.set_layer_binding.binding.param1 = 0x00070004
    wire = frame(req.SerializeToString())
    back = studio_pb2.Request()
    back.ParseFromString(_decode_frame(wire))
    assert back.request_id == 7
    assert back.keymap.set_layer_binding.binding.param1 == 0x00070004
    print("Request serialize/frame/parse OK")

    print("ALL SELF-TESTS PASSED")
