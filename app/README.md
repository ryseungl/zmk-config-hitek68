# Hitek68 Companion App

## Battery Monitor

Reads per-half battery levels from the Hitek68 dongle's vendor USB HID
interface and displays them in the terminal.

### Setup

```bash
pip install hidapi
```

No drivers needed on Windows/macOS/Linux — the vendor HID interface
(Usage Page 0xFF00) is not claimed by the OS as a keyboard.

### Usage

```bash
# Live dashboard (updates every ~2s, Ctrl+C to quit)
python hitek68_battery.py

# Single reading (useful for scripts/widgets)
python hitek68_battery.py --once
```

### Protocol

The dongle firmware (`config/src/battery_hid.c`) exposes a vendor-defined
HID interface (VID:PID `1D50:615E`, Usage Page `0xFF00`, Usage `0x01`)
that sends 3-byte input reports:

| Byte | Meaning                                    |
|------|--------------------------------------------|
| 0    | Report ID (`0x01`)                         |
| 1    | Left half battery % (0-100, `0xFF`=unknown)|
| 2    | Right half battery % (0-100, `0xFF`=unknown)|

Reports are sent on every battery change and re-sent every 3 seconds so
newly-connected readers get values quickly.

### Future

- Runtime debounce / deep-sleep controls (Phase 2)
- Keybind editor via ZMK Studio RPC (Phase 3)
