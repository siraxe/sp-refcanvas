"""Persist the REFCANVAS dock layout across Painter sessions."""
from __future__ import annotations

import os
import time

try:
    from .common import LOG_DIR, _log, _log_exc, _qt
except ImportError:
    from common import LOG_DIR, _log, _log_exc, _qt

QtCore, QtGui, QtWidgets = _qt()

LAYOUT_PATH = os.path.join(LOG_DIR, "dock_layout.bin")
_SAVE_DELAY_MS = 700
_SAVE_GATE = time.monotonic() + 3.0
_STATE = {"mw": None, "dock": None, "filter": None, "timer": None,
          "hooked": False, "quit_hooked": False}


def _write_layout(mw):
    """Write the main-window layout bytes to the state file."""
    try:
        data = bytes(mw.saveState())
    except Exception:
        _log_exc("dock layout capture")
        return False
    if not data:
        return False
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        temp = LAYOUT_PATH + ".tmp"
        with open(temp, "wb") as handle:
            handle.write(data)
        os.replace(temp, LAYOUT_PATH)
        return True
    except Exception:
        _log_exc("dock layout write")
        return False


def save_now():
    """Save the current dock layout immediately."""
    mw = _STATE.get("mw")
    if mw is None or _STATE.get("dock") is None:
        return False
    ok = _write_layout(mw)
    if ok:
        _log("dock layout saved")
    return ok


def _timer():
    """One dock-owned timer for debounced layout saves."""
    timer = _STATE.get("timer")
    if timer is None:
        timer = QtCore.QTimer(_STATE.get("dock"))
        timer.setSingleShot(True)
        timer.timeout.connect(_fire)
        _STATE["timer"] = timer
    return timer


def _fire():
    """Save once the debounce elapsed and no mouse button is down."""
    if _STATE.get("dock") is None:
        return
    left = _SAVE_GATE - time.monotonic()
    if left > 0:
        _timer().start(int(left * 1000) + 100)
        return
    try:
        app = QtWidgets.QApplication.instance()
        if (app is not None
                and app.mouseButtons() != QtCore.Qt.MouseButton.NoButton):
            _timer().start(400)
            return
    except Exception:
        pass
    save_now()


def schedule_save():
    """Schedule a debounced dock-layout save."""
    if _STATE.get("dock") is not None:
        _timer().start(_SAVE_DELAY_MS)


def _schedule(*_args):
    """Dock signal receiver for a debounced layout save."""
    schedule_save()


class _DockMoveFilter(QtCore.QObject):
    """Save floating dock moves and resizes."""

    def eventFilter(self, obj, event):
        try:
            if (event.type() in (QtCore.QEvent.Type.Move,
                                 QtCore.QEvent.Type.Resize)
                    and obj.isFloating()):
                schedule_save()
        except Exception:
            pass
        return False


def _hook(dock):
    if _STATE.get("hooked"):
        return
    _STATE["hooked"] = True
    try:
        dock.dockLocationChanged.connect(_schedule)
        dock.topLevelChanged.connect(_schedule)
        dock.visibilityChanged.connect(_schedule)
    except Exception:
        _log_exc("dock layout hooks")
    try:
        filt = _DockMoveFilter(dock)
        dock.installEventFilter(filt)
        _STATE["filter"] = filt
    except Exception:
        _log_exc("dock layout filter")


def _hook_quit():
    if _STATE.get("quit_hooked"):
        return
    _STATE["quit_hooked"] = True
    try:
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(save_now)
    except Exception:
        _log_exc("dock layout quit hook")


def attach(main_window, dock):
    """Restore the saved layout and start tracking dock changes."""
    _STATE["mw"] = main_window
    _STATE["dock"] = dock
    ok = False
    try:
        if os.path.isfile(LAYOUT_PATH):
            with open(LAYOUT_PATH, "rb") as handle:
                data = handle.read()
            if data:
                ok = bool(main_window.restoreState(data))
    except Exception:
        _log_exc("dock layout restore")
    try:
        dock.setVisible(True)
        dock.raise_()
    except Exception:
        pass
    _hook(dock)
    _hook_quit()
    _log("dock layout %s" % ("restored" if ok else "has no saved state"))
    return ok


def detach():
    """Stop tracking the dock and drop every Qt callback before teardown."""
    dock = _STATE.get("dock")
    timer = _STATE.get("timer")
    filt = _STATE.get("filter")
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
    if dock is not None:
        if filt is not None:
            try:
                dock.removeEventFilter(filt)
            except Exception:
                pass
        for name in ("dockLocationChanged", "topLevelChanged",
                     "visibilityChanged"):
            try:
                getattr(dock, name).disconnect(_schedule)
            except Exception:
                pass
    try:
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.disconnect(save_now)
    except Exception:
        pass
    _STATE["timer"] = None
    _STATE["filter"] = None
    _STATE["dock"] = None
    _STATE["mw"] = None
    _STATE["hooked"] = False
    _STATE["quit_hooked"] = False
