"""Base Color discovery and diagnostics helpers for the Live ON bridge."""
from __future__ import annotations

try:
    from .common import _qt
    from .qtbridge import (
        _alive, _class_name, _colour_kind, _colour_methods, _method_kinds,
        _method_signature, _method_type, _ptr, _prop_rows, _text, _walk)
except ImportError:
    from common import _qt
    from qtbridge import (
        _alive, _class_name, _colour_kind, _colour_methods, _method_kinds,
        _method_signature, _method_type, _ptr, _prop_rows, _text, _walk)

_QtCore, _QtGui, QtWidgets = _qt()

_COLOUR_SIGNALS = ("valuechanged", "colorchanged", "colourchanged")
_PROP_NAMES = ("value", "color", "colour", "basecolor", "base_color",
               "basecolour", "tint", "rgb", "rgba")
_SETTER_NAMES = ("setvalue", "setcolor", "setcolour", "setbasecolor",
                 "setbasecolour")
_BRUSH_WORDS = ("brush", "flow", "spacing", "jitter", "pressure",
                "airbrush", "smudge", "eraser", "clone", "dynamic stroke",
                "stroke", "sharpness")
_FILL_WORDS = ("projection", "tiling", "uv set", "uv tile", "planar",
               "tri-planar", "fill", "substance", "random seed",
               "physical size", "projection depth")


def _inside_refcanvas(widget):
    """True when a widget belongs to the RefCanvas panel."""
    try:
        node = widget
        for _ in range(40):
            if node is None:
                return False
            if str(node.objectName() or "") == "RefCanvasPanel":
                return True
            if "refcanvas" in _class_name(node).lower():
                return True
            node = node.parentWidget()
    except Exception:
        return False
    return False


def _dock_of(widget):
    """The dock-like parent of a widget, or None."""
    if widget is None:
        return None
    try:
        parent = widget.parentWidget()
        while parent is not None:
            if not _alive(parent):
                return None
            name = _class_name(parent).lower()
            if (isinstance(parent, QtWidgets.QDockWidget)
                    or "dockwidget" in name):
                return parent
            parent = parent.parentWidget()
    except Exception:
        pass
    return None


def _dock_title(widget):
    """Title of the dock or window hosting a widget."""
    dock = _dock_of(widget)
    try:
        if dock is not None:
            title = str(dock.windowTitle() or "")
            if title:
                return title
    except Exception:
        pass
    try:
        parent = widget.parentWidget()
        for _ in range(6):
            if parent is None or not _alive(parent):
                break
            title = str(parent.windowTitle() or "")
            if title:
                return title
            parent = parent.parentWidget()
    except Exception:
        pass
    return ""


def _in_properties(widget):
    """True when a widget sits in a dock or parameter panel."""
    if widget is None or _inside_refcanvas(widget):
        return False
    if _dock_of(widget) is not None:
        return True
    try:
        parent = widget.parentWidget()
        while parent is not None and _alive(parent):
            if _is_view(parent):
                return True
            parent = parent.parentWidget()
    except Exception:
        pass
    return False


def _is_view(widget):
    """True for a tool or material parameter view container."""
    name = _class_name(widget).lower()
    if not name or "preview" in name or "parameterspanel" in name:
        return False
    if "parametersview" in name or "propertiesview" in name:
        return True
    if "view" in name and ("material" in name or "tool" in name
                           or "parameter" in name):
        return True
    return "parameter" in name and "view" in name


def _is_colour_button(widget):
    """True for Painter's colour swatch button widgets."""
    name = _class_name(widget).lower()
    if not name or _inside_refcanvas(widget):
        return False
    if "popup" in name or "picker" in name:
        return False
    if "colorbutton" in name or "colourbutton" in name:
        return True
    if "color" in name or "colour" in name:
        return any(word in name for word in
                   ("button", "swatch", "chip", "selector"))
    return False


def _value_text(value):
    """Readable text for strings, enums and wrapped property values."""
    if isinstance(value, (str, bytes, bytearray)):
        return _text(value)
    if value is None:
        return ""
    parts = []
    for name in ("name", "value", "key", "string"):
        try:
            item = getattr(value, name)
            item = item() if callable(item) else item
            if isinstance(item, (str, bytes, bytearray)):
                parts.append(_text(item))
            elif isinstance(item, int):
                parts.append(str(item))
        except Exception:
            continue
    try:
        parts.append(str(value))
    except Exception:
        pass
    return " ".join(part for part in parts if part)


def _widget_texts(widget):
    """Lower-case labels and metadata found below a widget."""
    parts = []
    for item in [widget] + _walk(widget):
        if not _alive(item):
            continue
        try:
            parts.append(str(item.objectName() or ""))
        except Exception:
            pass
        try:
            if isinstance(item, QtWidgets.QLabel):
                parts.append(str(item.text() or ""))
            elif isinstance(item, QtWidgets.QAbstractButton):
                parts.append(str(item.text() or ""))
            elif isinstance(item, QtWidgets.QGroupBox):
                parts.append(str(item.title() or ""))
        except Exception:
            pass
        for name in ("title", "label", "channel", "valueName", "toolTip",
                     "accessibleName"):
            value = None
            try:
                value = item.property(name)
            except Exception:
                pass
            text = _value_text(value)
            if text:
                parts.append(text)
    return " ".join(part for part in parts if part).lower()


def _ancestor_text(widget):
    """Labels from nearby rows that hold only this colour button."""
    parts = []
    try:
        parent = widget.parentWidget()
    except Exception:
        return ""
    depth = 0
    while parent is not None and depth < 3 and _alive(parent):
        try:
            buttons = 0
            for item in _walk(parent):
                if _is_colour_button(item):
                    buttons += 1
                    if buttons > 1:
                        break
        except Exception:
            break
        if buttons != 1:
            break
        parts.append(_widget_texts(parent))
        try:
            parent = parent.parentWidget()
        except Exception:
            break
        depth += 1
    return " ".join(parts)


def _writable(prop):
    """True when a meta-property accepts writes."""
    try:
        return bool(prop.isWritable())
    except Exception:
        return False


def _prop_value(widget, name):
    """A property value, preferring the meta-property read."""
    if not _alive(widget):
        return None
    for _, prop_name, prop in _prop_rows(widget):
        if prop_name != name:
            continue
        try:
            value = prop.read(widget)
        except Exception:
            value = None
        if value is not None:
            return value
        break
    try:
        return widget.property(name)
    except Exception:
        return None


def _button_blob(button):
    """Searchable text for picking the Base Color button."""
    if not _alive(button):
        return ""
    parts = []
    for name in ("title", "label", "linkedChannel", "channel", "objectName"):
        text = _value_text(_prop_value(button, name))
        if text:
            parts.append(text)
    try:
        parts.append(str(button.objectName() or ""))
        parts.append(str(button.toolTip() or ""))
        parts.append(str(button.accessibleName() or ""))
        parts.append(str(button.statusTip() or ""))
        parts.append(str(button.whatsThis() or ""))
    except Exception:
        pass
    parts.append(_widget_texts(button))
    parts.append(_ancestor_text(button))
    return " ".join(part for part in parts if part).lower()


def _base_marked_text(blob):
    """True when searchable text names the Base Color channel."""
    return any(word in blob for word in
               ("base color", "basecolour", "base_color", "base-colour",
                "basecolor", "base colour", "base-color", "albedo"))


def _base_marked(button):
    """True when a colour button's metadata names the Base Color channel."""
    return _base_marked_text(_button_blob(button))


def _kind_from_text(text, title=""):
    """Classify a parameter view as brush, fill or unknown."""
    text = (text or "").lower()
    brush = sum(1 for word in _BRUSH_WORDS if word in text)
    fill = sum(1 for word in _FILL_WORDS if word in text)
    if "paint" in title or "brush" in title:
        brush += 2
    if "fill" in title:
        fill += 2
    if brush > fill:
        return "brush"
    if fill > brush:
        return "fill"
    return "unknown"


def _scan_view(view, visible, docked):
    """Collect labels and colour buttons for one parameter view."""
    title = _dock_title(view)
    parts = [title, _class_name(view)]
    buttons = []
    marked = []
    sources = 0
    for widget in _walk(view):
        if not _alive(widget):
            continue
        low = _class_name(widget).lower()
        try:
            if _is_colour_button(widget):
                buttons.append(widget)
                if _base_marked(widget):
                    marked.append(widget)
            if "sourceparametersview" in low:
                sources += 1
            if low.endswith("qlabel"):
                parts.append(str(widget.text() or ""))
            elif low.endswith("qgroupbox"):
                parts.append(str(widget.title() or ""))
            elif "button" in low:
                text = widget.text()
                if text:
                    parts.append(str(text))
        except Exception:
            continue
    kind = _kind_from_text(" ".join(parts), title.lower())
    score = (20.0 if visible else 0.0) + (4.0 if docked else 0.0)
    score += 8.0 if kind == "brush" else (-8.0 if kind == "fill" else 0.0)
    score += 60.0 if marked else 0.0
    score += min(len(marked), 2) * 6.0
    score += min(len(buttons), 6) * 0.5
    score += min(sources, 4) * 0.25
    return {
        "widget": view, "class": _class_name(view), "title": title,
        "visible": visible, "docked": docked, "kind": kind,
        "buttons": buttons, "marked": marked, "sources": sources,
        "score": score,
    }


def _candidate_views():
    """Every visible or docked tool and material parameter view."""
    app = QtWidgets.QApplication.instance()
    rows = []
    if app is None:
        return rows
    seen = set()
    for widget in app.allWidgets():
        try:
            if not _alive(widget) or not _is_view(widget):
                continue
            if _inside_refcanvas(widget):
                continue
            ptr = _ptr(widget)
            if ptr in seen:
                continue
            visible = bool(widget.isVisible())
            docked = _in_properties(widget)
            if not visible and not docked:
                continue
            seen.add(ptr)
            row = _scan_view(widget, visible, docked)
            if row["class"]:
                rows.append(row)
        except Exception:
            continue
    return rows


def _view_of(widget):
    """Nearest parameter view ancestor of a widget, or None."""
    try:
        parent = widget.parentWidget()
        while parent is not None and _alive(parent):
            if _is_view(parent):
                return parent
            parent = parent.parentWidget()
    except Exception:
        pass
    return None


def _marked_button(row):
    """Best Base-marked button in a view row."""
    buttons = [button for button in row.get("marked") or []
               if _alive(button)]
    if not buttons:
        return None

    def rank(item):
        index, button = item
        try:
            visible = 1 if button.isVisible() else 0
            enabled = 1 if button.isEnabled() else 0
        except Exception:
            visible = enabled = 0
        return (-visible, -enabled, index)

    return sorted(enumerate(buttons), key=rank)[0][1]


def _describe_view(view):
    """Compact view identity for the log."""
    if view is None:
        return "none"
    try:
        return "%s title=%r visible=%s docked=%s" % (
            _class_name(view), _dock_title(view), view.isVisible(),
            _in_properties(view))
    except Exception:
        return _class_name(view) or "dead view"


def _global_base_button():
    """A Base Color button for Painter builds with renamed view classes."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    marked = []
    fallback = None
    for order, widget in enumerate(app.allWidgets()):
        try:
            if not _alive(widget) or not _is_colour_button(widget):
                continue
            visible = bool(widget.isVisible())
            enabled = bool(widget.isEnabled())
            docked = _in_properties(widget)
            blob = _button_blob(widget)
            if _base_marked_text(blob):
                view = _view_of(widget)
                view_name = _class_name(view).lower() if view is not None else ""
                title = _dock_title(view).lower() if view is not None else ""
                score = (60.0 if visible else 0.0)
                score += 20.0 if enabled else 0.0
                score += 8.0 if docked else 0.0
                score += 15.0 if "brush" in view_name or "material" in view_name else 0.0
                score += 15.0 if "paint" in title else 0.0
                score -= 25.0 if any(word in view_name for word in
                                     ("source", "mask", "stencil")) else 0.0
                score -= 25.0 if "fill" in title else 0.0
                score -= order * 0.001
                marked.append((score, widget))
            elif (fallback is None and visible and enabled
                    and (docked or _view_of(widget) is not None)):
                fallback = widget
        except Exception:
            continue
    if marked:
        marked.sort(key=lambda item: item[0], reverse=True)
        return marked[0][1]
    return fallback


def _name_rank(name):
    """Preference among possible colour property names."""
    low = name.lower()
    if low == "value":
        return 0.0
    if low in ("color", "colour"):
        return 1.0
    if low in ("basecolor", "base_color", "basecolour"):
        return 2.0
    return 3.0


def _colour_prop(widget, need_write):
    """Best colour meta-property on a widget or its children."""
    if not _alive(widget):
        return None
    best = None
    best_score = None
    for candidate in [widget] + _walk(widget)[:300]:
        if not _alive(candidate):
            continue
        for index, name, prop in _prop_rows(candidate):
            if name.lower() not in _PROP_NAMES:
                continue
            kind = _colour_kind(_text(prop.typeName()), prop)
            if kind is None:
                continue
            writable = _writable(prop)
            if need_write and not writable:
                continue
            score = _name_rank(name)
            score += {"rgb3": 0.0, "rgb4": 0.0, "qcolor": 1.0,
                      "variant": 2.0}.get(kind, 3.0)
            if not writable:
                score += 2.0
            if _ptr(candidate) != _ptr(widget):
                score += 0.5
            if best_score is None or score < best_score:
                best = {"widget": candidate, "index": index, "name": name,
                        "prop": prop, "kind": kind, "writable": writable}
                best_score = score
    return best


def _colour_slot(button):
    """Best colour setter method on a button or its children."""
    if not _alive(button):
        return None
    best = None
    best_score = None
    for candidate in [button] + _walk(button)[:300]:
        if not _alive(candidate):
            continue
        for method in _colour_methods(candidate, _SETTER_NAMES):
            if _method_type(method) not in (0, 2):
                continue
            kinds = _method_kinds(method)
            if len(kinds) != 1:
                continue
            kind = _colour_kind(kinds[0])
            if kind is None:
                continue
            name = _text(method.name()).lower()
            score = {"setvalue": 0.0, "setcolor": 1.0, "setcolour": 1.0,
                     "setbasecolor": 2.0, "setbasecolour": 2.0}.get(name, 3.0)
            if _ptr(candidate) != _ptr(button):
                score += 0.5
            if best_score is None or score < best_score:
                best = {"widget": candidate, "method": method, "kind": kind,
                        "name": _text(method.name())}
                best_score = score
    return best


def _fallback_button(view):
    """A view widget with Base Color labels and a colour property."""
    if view is None:
        return None
    for widget in _walk(view)[:400]:
        try:
            if not _alive(widget):
                continue
            if not _base_marked_text(_widget_texts(widget)):
                continue
            if (_colour_prop(widget, False) is not None
                    or _colour_slot(widget) is not None):
                return widget
        except Exception:
            continue
    return None


def _base_button(view):
    """The Base Color button, preferring visible rows over collapsed ones."""
    if view is None or not _alive(view):
        return None
    shown = []
    hidden = []
    loose = []
    for order, widget in enumerate(_walk(view)):
        try:
            if not _alive(widget) or not _is_colour_button(widget):
                continue
            blob = _button_blob(widget)
            entry = (order, widget, blob, bool(widget.isVisible()),
                     bool(widget.isEnabled()))
            if _base_marked_text(blob):
                (shown if entry[3] else hidden).append(entry)
            elif entry[3]:
                loose.append(entry)
        except Exception:
            continue
    if shown:
        return shown[0][1]
    if hidden:
        return hidden[0][1]
    if loose:
        return loose[0][1]
    return _fallback_button(view)


def _interesting_props(button):
    """Property names, types and writability for diagnostics."""
    if not _alive(button):
        return "dead"
    bits = []
    for _, name, prop in _prop_rows(button):
        low = name.lower()
        if low not in _PROP_NAMES and low not in (
                "title", "label", "linkedchannel", "channel"):
            continue
        kind = _colour_kind(_text(prop.typeName()), prop) or "-"
        bits.append("%s:%s:%s%s" % (
            name, _text(prop.typeName()), kind,
            "" if _writable(prop) else "!"))
        if len(bits) >= 12:
            break
    return ", ".join(bits)


def _interesting_methods(button):
    """Colour signal and setter signatures for diagnostics."""
    if not _alive(button):
        return "dead"
    names = set(_COLOUR_SIGNALS) | set(_SETTER_NAMES)
    bits = [_method_signature(method)
            for method in _colour_methods(button, names)]
    return ", ".join(bits[:12])


def _describe(button, target=None, slot=None):
    """One-line description of Base Color discovery for the log."""
    if not _alive(button):
        return "dead widget"
    bits = ["props [%s]" % _interesting_props(button),
            "methods [%s]" % _interesting_methods(button)]
    try:
        bits.append("visible=%s" % bool(button.isVisible()))
    except Exception:
        pass
    if target is not None and _alive(target.get("widget")):
        bits.append("target %s.%s:%s#%d" % (
            _class_name(target["widget"]), target["name"], target["kind"],
            target["index"]))
    if slot is not None and _alive(slot.get("widget")):
        bits.append("setter %s.%s" % (
            _class_name(slot["widget"]), _method_signature(slot["method"])))
    return " ".join(bits)
