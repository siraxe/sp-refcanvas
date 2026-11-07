"""RefCanvas plugin lifecycle: create the dock and keep it alive."""
from __future__ import annotations

import os
import sys

__version__ = "0.1.0"

_STARTED = False
_state = {
    "panel": None,
    "dock": None,
    "timer": None,
    "tries": 0,
}

try:
    from .common import (_app, _log, _log_exc, _main_window, _qt, _qt_info,
                         _valid)
    from .dockstate import attach as _dock_attach
    from .dockstate import detach as _dock_detach
    from .dockstate import save_now as _dock_save
    from .panel import RefCanvasPanel, make_window_icon
except ImportError:
    from common import (_app, _log, _log_exc, _main_window, _qt, _qt_info,
                        _valid)
    from dockstate import attach as _dock_attach
    from dockstate import detach as _dock_detach
    from dockstate import save_now as _dock_save
    from panel import RefCanvasPanel, make_window_icon

QtCore, QtGui, QtWidgets = _qt()
_PANEL_TITLE = "REFCANVAS"


def _dock_of(widget):
    """Walk the parent chain to the QDockWidget hosting a panel."""
    try:
        parent = widget.parent()
        while parent is not None and not isinstance(parent,
                                                    QtWidgets.QDockWidget):
            parent = parent.parent()
        return parent
    except Exception:
        return None


def _add_panel():
    """Create and dock the panel; return True once it exists."""
    try:
        import substance_painter.ui as ui
        panel = _state.get("panel")
        if panel is not None and _valid(panel):
            dock = _state.get("dock")
            if dock is not None and _valid(dock):
                dock.show()
                dock.raise_()
            return True

        panel = RefCanvasPanel()
        dock = ui.add_dock_widget(panel)
        dock.setObjectName("RefCanvasDock")
        dock.setWindowTitle(_PANEL_TITLE)
        try:
            dock.setMinimumSize(panel.minimumSize())
        except Exception:
            _log_exc("dock minimum size")
        try:
            dock.setWindowIcon(make_window_icon())
        except Exception:
            pass

        main_window = _main_window()
        try:
            area = (main_window.dockWidgetArea(dock)
                    if main_window is not None
                    else QtCore.Qt.DockWidgetArea.NoDockWidgetArea)
            if (main_window is not None
                    and area == QtCore.Qt.DockWidgetArea.NoDockWidgetArea):
                main_window.addDockWidget(
                    QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        except Exception:
            _log_exc("initial dock placement")
        try:
            dock.show()
            dock.raise_()
        except Exception:
            _log_exc("initial dock show")
        if main_window is not None:
            try:
                _dock_attach(main_window, dock)
            except Exception:
                _log_exc("dock layout attach")

        _state["panel"] = panel
        _state["dock"] = dock
        _log("panel created (objectName=%r)" % panel.objectName())
        return True
    except Exception:
        _log_exc("panel creation")
        return False


def _retry():
    """Retry panel creation until Painter's UI service is ready."""
    if not _STARTED:
        return
    _state["tries"] += 1
    if _add_panel():
        timer = _state.get("timer")
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        return
    if _state["tries"] >= 120:
        timer = _state.get("timer")
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        _log("panel creation gave up after %d tries" % _state["tries"])


def _teardown():
    """Remove the dock and panel created by this plugin."""
    try:
        _dock_save()
    except Exception:
        _log_exc("dock layout save")
    try:
        _dock_detach()
    except Exception:
        _log_exc("dock layout detach")
    panel = _state.get("panel")
    dock = _state.get("dock")
    if panel is not None and _valid(panel):
        try:
            panel.flush_state()
        except Exception:
            _log_exc("panel state save")
    if dock is None and panel is not None and _valid(panel):
        dock = _dock_of(panel)
    try:
        import substance_painter.ui as ui
    except Exception:
        ui = None
    if panel is not None and _valid(panel):
        try:
            if ui is not None:
                ui.delete_ui_element(panel)
            else:
                panel.hide()
                panel.deleteLater()
        except Exception:
            _log_exc("panel removal")
        else:
            _log("teardown: panel removed")
    if dock is not None and _valid(dock):
        try:
            action = dock.toggleViewAction()
            main_window = _main_window()
            if main_window is not None:
                for menu in main_window.findChildren(QtWidgets.QMenu):
                    try:
                        menu.removeAction(action)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            main_window = _main_window()
            if main_window is not None:
                main_window.removeDockWidget(dock)
            if ui is not None:
                ui.delete_ui_element(dock)
            else:
                dock.deleteLater()
        except Exception:
            _log_exc("dock removal")
        else:
            _log("teardown: dock removed")
    _state["panel"] = None
    _state["dock"] = None


def _painter_version():
    """Painter version string for the plugin log."""
    try:
        import substance_painter.application as application
        try:
            return str(application.version())
        except Exception:
            return ".".join(str(part)
                            for part in application.version_info())
    except Exception:
        return "unknown"


def start_plugin():
    """Painter entry point: show the REFCANVAS dock."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    _log("start_plugin v%s pid=%d" % (__version__, os.getpid()))
    _log("versions: Painter %s; Python %s; %s"
         % (_painter_version(), sys.version.split()[0], _qt_info()))
    try:
        _qt()
    except Exception:
        _log_exc("Qt import")
        return
    if _app() is None:
        _log("start_plugin: no QApplication yet")
        return
    if _add_panel():
        return
    timer = QtCore.QTimer()
    timer.setInterval(500)
    timer.timeout.connect(_retry)
    _state["timer"] = timer
    timer.start()


def close_plugin():
    """Painter entry point: remove the REFCANVAS dock."""
    global _STARTED
    _log("close_plugin")
    _STARTED = False
    timer = _state.get("timer")
    if timer is not None:
        try:
            timer.stop()
            timer.deleteLater()
        except Exception:
            pass
    _state["timer"] = None
    _teardown()
