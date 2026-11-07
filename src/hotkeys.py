"""REFCANVAS hotkey settings: capture field, defaults and persistence."""
from __future__ import annotations

try:
    from . import store
    from .common import _qt
except ImportError:  # plugin loaded as a plain module, not a package
    import store
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()

# Action names with their factory defaults (display form uses ' + ').
HOTKEY_DEFAULTS = (
    ("Color Swap", "Shift + X"),
    ("Transform Layer", "Ctrl + T"),
    ("Add Swatch", "Alt + C"),
)

# Combos loaded once from the state store and kept updated on set_combo.
_COMBOS = None

# Master switch: when False every hotkey override is inert. Persisted
# alongside the combos and on by default.
_ENABLED = None


def _load():
    """Merge the saved combos over the defaults."""
    global _COMBOS, _ENABLED
    state = store.load_state()
    saved = state.get("hotkeys")
    combos = {}
    for name, default in HOTKEY_DEFAULTS:
        combo = None
        if isinstance(saved, dict):
            value = saved.get(name)
            if isinstance(value, str) and value.strip():
                combo = value.strip()
        combos[name] = combo or default
    _COMBOS = combos
    enabled = state.get("hotkeys_enabled")
    _ENABLED = enabled if isinstance(enabled, bool) else True
    return combos


def combo(name):
    """Current shortcut for an action name (loads the store once)."""
    if _COMBOS is None:
        _load()
    return _COMBOS.get(name, "")


def hotkeys_enabled():
    """True when the master hotkey switch is on (default)."""
    if _COMBOS is None:
        _load()
    return bool(_ENABLED)


def set_hotkeys_enabled(value):
    """Persist the master hotkey switch."""
    global _ENABLED
    if _COMBOS is None:
        _load()
    _ENABLED = bool(value)
    store.save_hotkeys_enabled(_ENABLED)


def set_combo(name, value):
    """Persist a new shortcut for an action name."""
    global _COMBOS
    if _COMBOS is None:
        _load()
    value = str(value or "").strip()
    if not value:
        return
    _COMBOS[name] = value
    data = store.load_state()
    saved = data.get("hotkeys")
    saved = dict(saved) if isinstance(saved, dict) else {}
    saved[name] = value
    store.save_hotkeys(saved)


def key_sequence(combo_text):
    """QKeySequence for a stored combo; Qt needs the compact form to parse."""
    compact = "".join(str(combo_text or "").split())
    if not compact:
        return QtGui.QKeySequence()
    try:
        sequence = QtGui.QKeySequence(compact)
    except Exception:
        return QtGui.QKeySequence()
    if sequence.isEmpty() or sequence.count() == 0:
        return QtGui.QKeySequence()
    try:
        if sequence[0].key() == QtCore.Qt.Key.Key_unknown:
            return QtGui.QKeySequence()
    except Exception:
        pass
    return sequence


def pen_icon(size=14):
    """Crisp filled pencil glyph (Material 'edit' shape) for capture buttons."""
    try:
        screen = QtWidgets.QApplication.primaryScreen()
        dpr = float(screen.devicePixelRatio()) if screen else 1.0
    except Exception:
        dpr = 1.0
    dpr = max(1.0, min(3.0, dpr))
    pixels = int(round(size * dpr))
    pixmap = QtGui.QPixmap(pixels, pixels)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        s = size / 24.0
        ink = QtGui.QColor(205, 205, 205)
        painter.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        painter.setBrush(QtGui.QBrush(ink))
        # Shaft plus tip: one five-point polygon.
        shaft = QtGui.QPolygonF([
            QtCore.QPointF(3.0 * s, 17.25 * s),
            QtCore.QPointF(3.0 * s, 21.0 * s),
            QtCore.QPointF(6.75 * s, 21.0 * s),
            QtCore.QPointF(17.81 * s, 9.94 * s),
            QtCore.QPointF(14.06 * s, 6.19 * s),
        ])
        painter.drawPolygon(shaft)
        # Eraser cap: rotated square at the top-right end.
        cap = QtGui.QPolygonF([
            QtCore.QPointF(15.47 * s, 4.78 * s),
            QtCore.QPointF(17.30 * s, 2.95 * s),
            QtCore.QPointF(21.05 * s, 6.70 * s),
            QtCore.QPointF(19.22 * s, 8.53 * s),
        ])
        painter.drawPolygon(cap)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


class HotkeyEdit(QtWidgets.QLineEdit):
    """Read-only shortcut field; the pen button starts key capture."""

    def __init__(self, text, on_changed, parent=None):
        super().__init__(text, parent)
        self._capturing = False
        self._before = text
        self._on_changed = on_changed
        self.setReadOnly(True)
        self.setMinimumWidth(150)

    def begin_capture(self):
        """Clear the field and grab the next key press."""
        self._before = self.text()
        self._capturing = True
        self.setText("")
        self.setPlaceholderText("Press a shortcut...")
        self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def _finish(self, combo=None):
        self._capturing = False
        self.setReadOnly(True)
        self.setPlaceholderText("")
        if combo is None:
            self.setText(self._before)
        else:
            self.setText(combo)
            self._on_changed(combo)

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)
        key = event.key()
        mods = event.modifiers()
        if key in (QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift,
                   QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Meta):
            return
        if key == QtCore.Qt.Key.Key_Escape:
            self._finish()
            return
        if key == QtCore.Qt.Key.Key_unknown:
            return
        name = QtGui.QKeySequence(int(key)).toString(
            QtGui.QKeySequence.SequenceFormat.NativeText)
        if not name:
            return
        parts = []
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & QtCore.Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & QtCore.Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & QtCore.Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")
        parts.append(name)
        self._finish(" + ".join(parts))

    def focusOutEvent(self, event):
        if self._capturing:
            self._finish()
        super().focusOutEvent(event)
