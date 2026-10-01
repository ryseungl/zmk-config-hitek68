"""ZMK keycode helpers for the Hitek68 Studio RPC client.

Keycodes are 32-bit values packed as::

    (mods << 24) | (page << 16) | usage_id

where ``page`` is the HID usage page (0x07 = Keyboard/Keypad,
0x0C = Consumer) and ``mods`` is a bitmask of implicit modifiers
(0x01 = left ctrl, 0x02 = left shift, 0x04 = left alt, 0x08 = left GUI).
"""

PAGE_KEYBOARD = 0x07
PAGE_CONSUMER = 0x0C

MOD_LCTRL = 0x01
MOD_LSHIFT = 0x02
MOD_LALT = 0x04
MOD_LGUI = 0x08


def _kc(usage, page=PAGE_KEYBOARD, mods=0):
    """Pack a 32-bit keycode from usage/page/mods."""
    return (mods << 24) | (page << 16) | usage


# --- Letters (HID usage 0x04 - 0x1D) ----------------------------------------
_LETTERS = {
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08,
    "F": 0x09, "G": 0x0A, "H": 0x0B, "I": 0x0C, "J": 0x0D,
    "K": 0x0E, "L": 0x0F, "M": 0x10, "N": 0x11, "O": 0x12,
    "P": 0x13, "Q": 0x14, "R": 0x15, "S": 0x16, "T": 0x17,
    "U": 0x18, "V": 0x19, "W": 0x1A, "X": 0x1B, "Y": 0x1C,
    "Z": 0x1D,
}

# --- Numbers (HID usage 0x1E - 0x27) ----------------------------------------
_NUMBERS = {
    "N1": 0x1E, "N2": 0x1F, "N3": 0x20, "N4": 0x21, "N5": 0x22,
    "N6": 0x23, "N7": 0x24, "N8": 0x25, "N9": 0x26, "N0": 0x27,
}

# --- Function keys (0x3A - 0x45, 0x68 - 0x73) --------------------------------
_FUNCTIONS = {
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D,
    "F5": 0x3E, "F6": 0x3F, "F7": 0x40, "F8": 0x41,
    "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    "F13": 0x68, "F14": 0x69, "F15": 0x6A, "F16": 0x6B,
    "F17": 0x6C, "F18": 0x6D, "F19": 0x6E, "F20": 0x6F,
    "F21": 0x70, "F22": 0x71, "F23": 0x72, "F24": 0x73,
}

# --- Common keys -------------------------------------------------------------
_COMMON = {
    "ENTER": 0x28, "RET": 0x28,
    "ESC": 0x29, "ESCAPE": 0x29,
    "BSPC": 0x2A, "BACKSPACE": 0x2A,
    "TAB": 0x2B,
    "SPACE": 0x2C, "SPC": 0x2C,
    "CAPS": 0x39, "CAPSLOCK": 0x39,
    "PSCRN": 0x46, "PRINTSCREEN": 0x46,
    "SLCK": 0x47, "SCROLLLOCK": 0x47,
    "PAUSE": 0x48, "BREAK": 0x48,
    "INS": 0x49, "INSERT": 0x49,
    "HOME": 0x4A,
    "PG_UP": 0x4B, "PGUP": 0x4B,
    "DEL": 0x4C, "DELETE": 0x4C,
    "END": 0x4D,
    "PG_DN": 0x4E, "PGDN": 0x4E,
    "RIGHT": 0x4F, "LEFT": 0x50, "DOWN": 0x51, "UP": 0x52,
    "APP": 0x65,  # Application / context menu
}

# --- Base symbols (unshifted HID usages) --------------------------------------
_SYMBOLS = {
    "MINUS": 0x2D,
    "EQUAL": 0x2E,
    "LBKT": 0x2F,   # [
    "RBKT": 0x30,   # ]
    "BSLH": 0x31,   # backslash
    "SEMI": 0x33,   # ;
    "SQT": 0x34,    # '
    "GRAVE": 0x35,  # `
    "COMMA": 0x36,
    "DOT": 0x37,
    "FSLH": 0x38,   # /
}

# --- Shifted symbols: (usage of base key, with left-shift modifier) ------------
# e.g. "!" = shift + "1", "~" = shift + "`"
_SHIFTED_SYMBOLS = {
    "EXCL": ("N1",),        # !
    "AT": ("N2",),          # @
    "HASH": ("N3",),        # #
    "DOLLAR": ("N4",),      # $
    "PRCNT": ("N5",),       # %
    "CARET": ("N6",),       # ^
    "AMPS": ("N7",),        # &
    "STAR": ("N8",),        # *
    "LPAR": ("N9",),        # (
    "RPAR": ("N0",),        # )
    "UNDERSCORE": ("MINUS",),   # _
    "PLUS": ("EQUAL",),         # +
    "LBRC": ("LBKT",),          # {
    "RBRC": ("RBKT",),          # }
    "PIPE": ("BSLH",),          # |
    "COLON": ("SEMI",),         # :
    "DQT": ("SQT",),            # "
    "TILDE": ("GRAVE",),        # ~
    "LT": ("COMMA",),           # <
    "GT": ("DOT",),             # >
    "QUESTION": ("FSLH",),      # ?
}

# --- Modifier keys -------------------------------------------------------------
_MODIFIERS = {
    "LCTRL": 0xE0, "LSHIFT": 0xE1, "LALT": 0xE2, "LGUI": 0xE3,
    "RCTRL": 0xE4, "RSHIFT": 0xE5, "RALT": 0xE6, "RGUI": 0xE7,
}

# --- Consumer (media) keys, HID usage page 0x0C --------------------------------
_CONSUMER = {
    "C_PP": 0xCD,        # Play/Pause
    "C_NEXT": 0xB5,      # Scan Next Track
    "C_PREV": 0xB6,      # Scan Previous Track
    "C_STOP": 0xB7,      # Stop
    "C_MUTE": 0xE2,      # Mute
    "C_VOL_UP": 0xE9,    # Volume Increment
    "C_VOL_DN": 0xEA,    # Volume Decrement
    "C_BRI_UP": 0x6F,    # Brightness Increment
    "C_BRI_DN": 0x70,    # Brightness Decrement
    "C_EJCT": 0xB8,      # Eject
}

# --- Special --------------------------------------------------------------------
_SPECIAL = {
    "NONE": 0x00000000,  # no binding
    "TRANS": 0xFFFFFFFF,  # transparent (fall through to lower layer)
}


def _build_table():
    table = {}
    for name, usage in _LETTERS.items():
        table[name] = _kc(usage)
    for name, usage in _NUMBERS.items():
        table[name] = _kc(usage)
    for name, usage in _FUNCTIONS.items():
        table[name] = _kc(usage)
    for name, usage in _COMMON.items():
        table[name] = _kc(usage)
    for name, usage in _SYMBOLS.items():
        table[name] = _kc(usage)
    for name, usage in _MODIFIERS.items():
        table[name] = _kc(usage)
    for name, usage in _CONSUMER.items():
        table[name] = _kc(usage, page=PAGE_CONSUMER)
    for name, (base,) in _SHIFTED_SYMBOLS.items():
        base_usage = table[base] & 0xFFFF
        table[name] = _kc(base_usage, mods=MOD_LSHIFT)
    for name, value in _SPECIAL.items():
        table[name] = value
    return table


KEYCODES = _build_table()

# Reverse lookup: value -> name (first name wins on duplicates).
_KEYCODE_NAMES = {}
for _name, _value in KEYCODES.items():
    _KEYCODE_NAMES.setdefault(_value, _name)


def keycode(name):
    """Return the 32-bit keycode value for a key name (case-insensitive).

    Raises KeyError if the name is unknown.
    """
    return KEYCODES[name.strip().upper()]


def keycode_name(value):
    """Return the key name for a 32-bit keycode value, or a hex string.

    Handles shifted variants even when only the base key is in the table.
    """
    value = value & 0xFFFFFFFF
    if value in _KEYCODE_NAMES:
        return _KEYCODE_NAMES[value]
    mods = (value >> 24) & 0xFF
    page = (value >> 16) & 0xFF
    usage = value & 0xFFFF
    base = _kc(usage, page=page)
    base_name = _KEYCODE_NAMES.get(base)
    if base_name:
        mod_names = []
        if mods & MOD_LCTRL:
            mod_names.append("CTRL")
        if mods & MOD_LSHIFT:
            mod_names.append("SHIFT")
        if mods & MOD_LALT:
            mod_names.append("ALT")
        if mods & MOD_LGUI:
            mod_names.append("GUI")
        return "+".join(mod_names) + "+" + base_name if mod_names else base_name
    return "0x%08X" % value


__all__ = ["KEYCODES", "keycode", "keycode_name",
           "PAGE_KEYBOARD", "PAGE_CONSUMER"]
