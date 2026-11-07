"""REFCANVAS settings dialog: wheel corner and colour pick modifiers."""
from __future__ import annotations

try:
    from . import hotkeys
    from .common import _qt
except ImportError:  # plugin loaded as a plain module, not a package
    import hotkeys
    from common import _qt

try:
    from . import __version__
except ImportError:  # plugin loaded as a plain module, not a package
    try:
        from __init__ import __version__
    except Exception:
        __version__ = "0.1.0"


WHEEL_CORNERS = ("bottom left", "bottom right", "top left", "top right")

ISSUES_URL = "https://github.com/siraxe/sp-refcanvas"


def show_settings(parent=None, wheel_corner="bottom left", alt_pick=True,
                  on_wheel_corner=None, on_alt_pick=None,
                  on_hotkey_changed=None, on_hotkeys_enabled=None):
    """Open the settings dialog; changes apply live through the callbacks."""
    QtCore, _QtGui, QtWidgets = _qt()

    if parent is not None:
        try:
            parent = parent.window()
        except RuntimeError:
            parent = None
    if parent is None:
        try:
            parent = QtWidgets.QApplication.activeWindow()
        except Exception:
            parent = None

    if wheel_corner not in WHEEL_CORNERS:
        wheel_corner = "bottom left"

    dialog = QtWidgets.QDialog(parent)
    dialog.setObjectName("RefCanvasSettingsDialog")
    dialog.setWindowTitle("REFCANVAS Settings")
    # Destroy the dialog as soon as it closes; a lingering hidden window on
    # Painter's main window makes Painter report an unclean shutdown.
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
    try:
        dialog.setWindowFlag(
            QtCore.Qt.WindowType.WindowContextHelpButtonHint, False)
    except Exception:
        pass
    dialog.setStyleSheet(
        "QDialog { background: #2d2d2d; }"
        "QLabel { color: #c8c8c8; font-size: 10px; }"
        "QCheckBox { color: #c8c8c8; font-size: 10px; spacing: 6px; }"
        "QCheckBox::indicator { width: 13px; height: 13px; }"
        "QComboBox { background: #242424; color: #d2d2d2;"
        " border: 1px solid #0d0d0d; border-radius: 2px;"
        " padding: 2px 14px 2px 6px; font-size: 10px; min-height: 16px; }"
        "QComboBox:hover { border-color: #4d6ba3; }"
        "QComboBox::drop-down { border: none; width: 14px; }"
        "QComboBox::down-arrow { image: none;"
        " border-left: 3px solid transparent;"
        " border-right: 3px solid transparent;"
        " border-top: 4px solid #b5b5b5; width: 0px; height: 0px; }"
        "QComboBox QAbstractItemView { background: #2b2b2b; color: #d2d2d2;"
        " border: 1px solid #454545;"
        " selection-background-color: #46537c; }"
        "QPushButton { background: #2b2b2b; color: #d2d2d2;"
        " border: 1px solid #0d0d0d; border-radius: 3px;"
        " padding: 3px 14px; font-size: 10px; }"
        "QPushButton:hover { background: #383838; }"
        "QLineEdit { background: #242424; color: #d2d2d2;"
        " border: 1px solid #0d0d0d; border-radius: 2px;"
        " padding: 2px 6px; font-size: 10px;"
        " selection-background-color: #46537c; }"
        "QLineEdit:focus { border-color: #4d6ba3; }"
        "QToolButton { background: transparent; border: none; }")

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(14, 12, 14, 10)
    layout.setSpacing(10)

    corner_label = QtWidgets.QLabel("Wheel snap corner:", dialog)
    corner_combo = QtWidgets.QComboBox(dialog)
    corner_combo.addItems(list(WHEEL_CORNERS))
    corner_combo.setCurrentText(wheel_corner)
    corner_row = QtWidgets.QHBoxLayout()
    corner_row.setContentsMargins(4, 0, 4, 0)
    corner_row.setSpacing(10)
    corner_row.addWidget(corner_label)
    corner_row.addWidget(corner_combo)
    corner_row.addStretch(1)
    layout.addLayout(corner_row)

    switches = QtWidgets.QHBoxLayout()
    switches.setContentsMargins(4, 0, 4, 0)
    switches.setSpacing(18)
    alt_check = QtWidgets.QCheckBox("Alt for color pick", dialog)
    alt_check.setChecked(bool(alt_pick))
    alt_check.setToolTip(
        "When checked, colour picking needs Alt held (eyedropper cursor)."
        " When unchecked, a plain left-click drag on the canvas picks"
        " colours and the cursor never changes.")
    enable_check = QtWidgets.QCheckBox("Enable hotkeys", dialog)
    enable_check.setChecked(hotkeys.hotkeys_enabled())
    enable_check.setToolTip(
        "When unchecked, none of the shortcuts below are active in Painter.")
    switches.addWidget(alt_check)
    switches.addWidget(enable_check)
    switches.addStretch(1)
    layout.addLayout(switches)

    def _corner_changed(text):
        if on_wheel_corner is not None:
            on_wheel_corner(str(text))

    def _alt_toggled(on):
        if on_alt_pick is not None:
            on_alt_pick(bool(on))

    corner_combo.currentTextChanged.connect(_corner_changed)
    alt_check.toggled.connect(_alt_toggled)

    hotkeys_label = QtWidgets.QLabel("<b>Hotkeys:</b>", dialog)
    layout.addWidget(hotkeys_label)

    def _hotkey_changed(name, value):
        hotkeys.set_combo(name, value)
        if on_hotkey_changed is not None:
            on_hotkey_changed(name, value)

    grid = QtWidgets.QGridLayout()
    grid.setContentsMargins(4, 0, 4, 0)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(6)
    pen = hotkeys.pen_icon()
    hotkey_rows = []
    for row, (name, _default) in enumerate(hotkeys.HOTKEY_DEFAULTS):
        field = hotkeys.HotkeyEdit(
            hotkeys.combo(name),
            lambda value, n=name: _hotkey_changed(n, value), dialog)
        button = QtWidgets.QToolButton(dialog)
        button.setIcon(pen)
        button.setIconSize(QtCore.QSize(14, 14))
        button.setAutoRaise(True)
        button.setFixedSize(24, 24)
        button.setToolTip("Click, then press the shortcut for %s" % name)
        button.clicked.connect(
            lambda checked=False, f=field: f.begin_capture())
        label = QtWidgets.QLabel(name + ":", dialog)
        grid.addWidget(label, row, 0)
        grid.addWidget(field, row, 1)
        grid.addWidget(button, row, 2)
        hotkey_rows.append((label, field, button))
    layout.addLayout(grid)

    def _apply_hotkey_switch(on):
        # Grey out the rows so it is obvious the shortcuts are inert.
        for row_label, field, button in hotkey_rows:
            row_label.setEnabled(on)
            field.setEnabled(on)
            button.setEnabled(on)

    def _enable_toggled(on):
        hotkeys.set_hotkeys_enabled(bool(on))
        _apply_hotkey_switch(bool(on))
        if on_hotkeys_enabled is not None:
            on_hotkeys_enabled(bool(on))

    enable_check.toggled.connect(_enable_toggled)
    _apply_hotkey_switch(enable_check.isChecked())

    # About: compact plugin info in small grey text with an issues link.
    line = QtWidgets.QFrame(dialog)
    line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    layout.addWidget(line)

    about = QtWidgets.QLabel(
        '<span style="color:#8f8f8f; font-size:9px;">'
        'REFCANVAS v%s'
        '<br>Reference images for Substance 3D Painter'
        '<br><a href="%s" style="color:#7d93b8; font-size:9px;">'
        'Report an issue on GitHub</a></span>'
        % (__version__, ISSUES_URL), dialog)
    about.setOpenExternalLinks(True)
    about.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
    about.setContentsMargins(4, 4, 4, 0)
    layout.addWidget(about)

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)

    dialog.exec()
    try:
        dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete)
    except Exception:
        pass
