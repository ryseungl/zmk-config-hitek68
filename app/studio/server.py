"""Hitek68 Studio keybind editor - web server.

Serves the visual keymap editor and bridges it to the dongle over Studio RPC.
Run:  python3 server.py   (then open http://localhost:5000)
"""

import sys
import os
import json
from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import Studio, StudioError, find_studio_port
import keycodes

app = Flask(__name__, static_folder="static", static_url_path="/static")

_studio = None


def get_studio():
    global _studio
    if _studio is None:
        port = find_studio_port()
        if not port:
            raise StudioError("No Studio RPC device found")
        _studio = Studio(port=port)
    return _studio


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def status():
    try:
        st = get_studio()
        lock = st.get_lock_state()
        return jsonify({"connected": True, "port": st.port, "unlocked": lock == 1})
    except Exception as e:
        return jsonify({"connected": False, "error": str(e)})


@app.route("/api/keymap")
def api_keymap():
    st = get_studio()
    km = st.get_keymap()
    layers = []
    for layer in km.layers:
        bindings = [
            {
                "behavior_id": b.behavior_id,
                "param1": b.param1,
                "param2": b.param2,
            }
            for b in layer.bindings
        ]
        layers.append({"id": layer.id, "name": layer.name, "bindings": bindings})
    return jsonify({"layers": layers})


@app.route("/api/layout")
def api_layout():
    # Physical layout: w, h, x, y per position (from hitek68-layouts.dtsi).
    # Zero-size entries are unpopulated matrix positions.
    layout_path = os.path.join(os.path.dirname(__file__), "layout.json")
    with open(layout_path) as f:
        return jsonify(json.load(f))


@app.route("/api/behaviors")
def api_behaviors():
    st = get_studio()
    out = []
    for bid in st.list_behaviors():
        try:
            d = st.get_behavior_details(bid)
            out.append(
                {
                    "id": bid,
                    "name": d.display_name or "",
                    "params": [
                        {"name": p.name, "type": str(p.type)}
                        for p in getattr(d.metadata, "params", [])
                    ],
                }
            )
        except Exception:
            out.append({"id": bid, "name": "", "params": []})
    return jsonify({"behaviors": out})


@app.route("/api/binding", methods=["POST"])
def api_set_binding():
    data = request.get_json(force=True)
    st = get_studio()
    ok = st.set_binding(
        layer_id=int(data["layer_id"]),
        position=int(data["position"]),
        behavior_id=int(data["behavior_id"]),
        param1=int(data.get("param1", 0)),
        param2=int(data.get("param2", 0)),
    )
    return jsonify({"ok": ok})


@app.route("/api/save", methods=["POST"])
def api_save():
    st = get_studio()
    return jsonify({"ok": st.save_changes()})


@app.route("/api/discard", methods=["POST"])
def api_discard():
    st = get_studio()
    return jsonify({"ok": st.discard_changes()})


@app.route("/api/unsaved")
def api_unsaved():
    st = get_studio()
    return jsonify({"unsaved": st.check_unsaved_changes()})


@app.route("/api/keycodes")
def api_keycodes():
    return jsonify(keycodes.KEYCODES)


# ---- Battery (USB HID vendor interface) ----

DONGLE_VID = 0x1D50
DONGLE_PID = 0x615E
VENDOR_USAGE_PAGE = 0xFF00
VENDOR_USAGE = 0x01
BATTERY_REPORT_ID = 0x01
BATTERY_UNKNOWN = 0xFF


def _find_vendor_device():
    try:
        import hid
    except ImportError:
        return None
    for dev in hid.enumerate(DONGLE_VID, DONGLE_PID):
        if (dev.get("usage_page") == VENDOR_USAGE_PAGE
                and dev.get("usage") == VENDOR_USAGE):
            return dev["path"]
    return None


@app.route("/api/battery")
def api_battery():
    try:
        import hid as hidapi
    except ImportError:
        return jsonify({"connected": False, "left": None, "right": None,
                        "error": "hidapi not installed (pip install hidapi)"})
    path = _find_vendor_device()
    if not path:
        return jsonify({"connected": False, "left": None, "right": None})
    try:
        h = hidapi.device()
        h.open_path(path)
        h.set_nonblocking(False)
        data = h.read(3, timeout_ms=3000)
        h.close()
    except (OSError, IOError):
        return jsonify({"connected": False, "left": None, "right": None})
    if not data or len(data) < 3 or data[0] != BATTERY_REPORT_ID:
        return jsonify({"connected": True, "left": None, "right": None})
    left = None if data[1] == BATTERY_UNKNOWN else data[1]
    right = None if data[2] == BATTERY_UNKNOWN else data[2]
    return jsonify({"connected": True, "left": left, "right": right})


# ---- Sleep timeout (USB HID output report, relayed to halves) ----

import struct

REPORT_ID_COMMAND = 0x02
CMD_SET_SLEEP = 0x02
SLEEP_TARGETS = {"both": 0, "left": 1, "right": 2}


@app.route("/api/sleep", methods=["POST"])
def api_sleep():
    data = request.get_json(force=True)
    timeout_ms = int(data.get("timeout_ms", 0))
    target = SLEEP_TARGETS.get(data.get("target", "both"), 0)
    if timeout_ms != 0 and timeout_ms < 60000:
        return jsonify({"ok": False, "error": "timeout must be 0 or >= 60000ms"}), 400

    path = _find_vendor_device()
    if not path:
        return jsonify({"ok": False, "error": "dongle not found"}), 404

    try:
        import hid as hidapi
    except ImportError:
        return jsonify({"ok": False, "error": "hidapi not installed (pip install hidapi)"}), 500

    report = bytes([REPORT_ID_COMMAND, CMD_SET_SLEEP, target]) + struct.pack("<I", timeout_ms) + b"\x00"
    report = report[:8].ljust(8, b"\x00")
    try:
        h = hidapi.device()
        h.open_path(path)
        h.write(report)
        h.close()
    except (OSError, IOError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
