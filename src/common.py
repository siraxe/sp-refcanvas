"""Shared logging and Qt helpers for RefCanvas."""
from __future__ import annotations

import importlib
import os
import threading
import time
import traceback

LOG_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "refcanvas")
LOG_PATH = os.path.join(LOG_DIR, "refcanvas.log")
_LOG_LOCK = threading.Lock()
_QT = None
_QT_BINDING = ""
_SHIBOKEN = None
_SHIBOKEN_TRIED = False


def _log(message):
    """Append one short line to the plugin log."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with _LOG_LOCK:
            with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
                fh.write("%s [%d] %s\n" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), message))
    except Exception:
        pass


def _log_exc(what):
    """Log one failed operation and its traceback."""
    _log("%s failed: %s" % (
        what, traceback.format_exc().replace("\n", " | ")))


def _add_event_position(QtCore, QtGui):
    """Give Qt5 events the Qt6 position helpers used by the panel."""
    if hasattr(QtGui.QMouseEvent, "position"):
        return

    def local_point(event):
        pos = event.localPos() if hasattr(event, "localPos") else event.pos()
        return QtCore.QPointF(pos)

    def screen_point(event):
        pos = event.screenPos() if hasattr(event, "screenPos") else event.pos()
        return QtCore.QPointF(pos)

    def wheel_point(event):
        pos = event.posF() if hasattr(event, "posF") else event.pos()
        return QtCore.QPointF(pos)

    def drop_point(event):
        pos = event.posF() if hasattr(event, "posF") else event.pos()
        return QtCore.QPointF(pos)

    try:
        QtGui.QMouseEvent.position = local_point
        QtGui.QMouseEvent.globalPosition = screen_point
        QtGui.QWheelEvent.position = wheel_point
        QtGui.QDropEvent.position = drop_point
    except Exception:
        _log_exc("Qt5 event helpers")


def _qt():
    """Import and cache the Painter Qt binding (PySide6 or PySide2)."""
    global _QT, _QT_BINDING
    if _QT is None:
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
            _QT_BINDING = "PySide6"
        except ImportError:
            from PySide2 import QtCore, QtGui, QtWidgets
            _QT_BINDING = "PySide2"
        _add_event_position(QtCore, QtGui)
        _QT = (QtCore, QtGui, QtWidgets)
    return _QT


def _shiboken():
    """Return shiboken6 or shiboken2, whichever Painter provides."""
    global _SHIBOKEN, _SHIBOKEN_TRIED
    if not _SHIBOKEN_TRIED:
        _SHIBOKEN_TRIED = True
        for name in ("shiboken6", "shiboken2"):
            try:
                _SHIBOKEN = importlib.import_module(name)
                break
            except Exception:
                continue
    return _SHIBOKEN


def _qt_info():
    """Binding name and Qt version for the plugin log."""
    try:
        QtCore, _QtGui, _QtWidgets = _qt()
        return "%s Qt %s" % (_QT_BINDING, QtCore.qVersion())
    except Exception:
        return "Qt unavailable"


def _valid(widget):
    """True while a PySide wrapper still points at a live object."""
    try:
        widget.objectName()
        return True
    except Exception:
        return False


def _app():
    """Return the running QApplication or None."""
    _QtCore, _QtGui, QtWidgets = _qt()
    return QtWidgets.QApplication.instance()


def _main_window():
    """Return Painter's main window, or None during early startup."""
    try:
        import substance_painter.ui as ui
        return ui.get_main_window()
    except Exception:
        return None
