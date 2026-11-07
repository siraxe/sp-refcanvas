"""JSON persistence for swatches and the saved reference document."""
from __future__ import annotations

import json
import os

try:
    from .common import LOG_DIR, _log_exc
except ImportError:
    from common import LOG_DIR, _log_exc

STATE_PATH = os.path.join(LOG_DIR, "state.json")
LAYER_DIR = os.path.join(LOG_DIR, "layers")
VERSION = 1


def load_state():
    """Return the saved plugin state, or an empty dict."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        _log_exc("state load")
        return {}


def write_state(data):
    """Write the plugin state JSON atomically."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        temp = STATE_PATH + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        os.replace(temp, STATE_PATH)
        return True
    except Exception:
        _log_exc("state save")
        return False


def save_swatches(colors, next_index):
    """Persist the swatch slots and the write cursor."""
    data = load_state()
    data["version"] = VERSION
    data["swatches"] = list(colors)
    data["swatch_next"] = int(next_index)
    return write_state(data)


def save_controls(main, secondary, live_on, wheel_open=None):
    """Persist the two top-row colours, Live On and the wheel flag."""
    data = load_state()
    data["version"] = VERSION
    data["colors"] = {"main": str(main), "secondary": str(secondary)}
    data["live_on"] = bool(live_on)
    if wheel_open is not None:
        data["wheel_open"] = bool(wheel_open)
    return write_state(data)


def save_hotkeys(hotkeys):
    """Persist the action shortcut combos."""
    data = load_state()
    data["version"] = VERSION
    data["hotkeys"] = dict(hotkeys)
    return write_state(data)


def save_hotkeys_enabled(enabled):
    """Persist the master hotkey switch."""
    data = load_state()
    data["version"] = VERSION
    data["hotkeys_enabled"] = bool(enabled)
    return write_state(data)


def save_wheel_corner(corner):
    """Persist the wheel panel snap corner."""
    data = load_state()
    data["version"] = VERSION
    data["wheel_corner"] = str(corner)
    return write_state(data)


def save_alt_pick(required):
    """Persist whether Alt is required for canvas colour picking."""
    data = load_state()
    data["version"] = VERSION
    data["alt_pick"] = bool(required)
    return write_state(data)


def save_document(document):
    """Persist document metadata; layer pixels live in separate files."""
    data = load_state()
    data["version"] = VERSION
    data["document"] = document
    return write_state(data)


def prune_layer_files(keep):
    """Delete saved layer images that are no longer referenced."""
    try:
        if not os.path.isdir(LAYER_DIR):
            return
        keep = set(keep or ())
        for name in os.listdir(LAYER_DIR):
            if name.lower().endswith(".png") and name not in keep:
                os.remove(os.path.join(LAYER_DIR, name))
    except Exception:
        _log_exc("layer files prune")


def clear_document():
    """Drop the saved document metadata and every layer image."""
    data = load_state()
    data.pop("document", None)
    ok = write_state(data)
    prune_layer_files(())
    return ok
