"""Live ON bridge: write picked REFCANVAS colours into the paint Base Color."""
from __future__ import annotations

try:
    from .common import _log, _log_exc, _qt
    from .qtbridge import (
        _alive, _as_colour, _class_name, _close, _linear, _method_kinds,
        _method_signature, _ptr, _raw_invoke_method, _raw_values,
        _raw_write_target, set_fault_callback)
    from .liveprobe import (
        _base_button, _candidate_views, _colour_prop, _colour_slot, _describe,
        _describe_view, _global_base_button, _marked_button)
except ImportError:
    from common import _log, _log_exc, _qt
    from qtbridge import (
        _alive, _as_colour, _class_name, _close, _linear, _method_kinds,
        _method_signature, _ptr, _raw_invoke_method, _raw_values,
        _raw_write_target, set_fault_callback)
    from liveprobe import (
        _base_button, _candidate_views, _colour_prop, _colour_slot, _describe,
        _describe_view, _global_base_button, _marked_button)

QtCore, QtGui, QtWidgets = _qt()

_STATE = {
    "seq": 0,
    "color": None,
    "view": None,
    "button": None,
    "target": None,
    "slot": None,
    "sig": None,
    "diag": None,
    "write_fail": None,
    "retried": None,
    "widget_refs": [],
}


def _diag(key, message):
    """Log one discovery problem once per distinct key."""
    if _STATE.get("diag") == key:
        return
    _STATE["diag"] = key
    _log("live: " + message)


def _hold(*widgets):
    """Keep Python references to discovered widgets so wrappers stay valid."""
    refs = _STATE.setdefault("widget_refs", [])
    for widget in widgets:
        if widget is None or not _alive(widget):
            continue
        pointer = _ptr(widget)
        if all(pointer != _ptr(existing) for existing in refs):
            refs.append(widget)
    if len(refs) > 24:
        del refs[:-24]


def _discover():
    """Find the active paint Base Color target."""
    rows = _candidate_views()
    rows = [row for row in rows if _alive(row.get("widget"))]
    rows.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    view = None
    button = None
    if rows:
        best = rows[0]
        if best.get("kind") == "fill":
            _diag(("fill", _ptr(best["widget"])),
                  "active view is a fill view (%s); skipped"
                  % _describe_view(best["widget"]))
            return None
        for row in rows:
            if row.get("kind") == "fill":
                continue
            candidate = _marked_button(row)
            if candidate is not None:
                view, button = row["widget"], candidate
                break
        if button is None:
            for row in rows:
                if row.get("kind") == "fill":
                    continue
                candidate = _base_button(row["widget"])
                if candidate is not None:
                    view, button = row["widget"], candidate
                    break
        if button is None:
            candidate = _global_base_button()
            if candidate is not None:
                view, button = candidate, candidate
        if button is None:
            _diag(("button", _ptr(best["widget"])),
                  "no Base Color button in %d parameter view(s)" % len(rows))
            return None
    else:
        _diag(("views",), "no material or tool parameter view")
        button = _global_base_button()
        if button is None:
            _diag(("global",), "no parameter view or Base Color button found")
            return None
        view = button
    target = _colour_prop(button, True)
    slot = None
    if target is None:
        slot = _colour_slot(button)
        target = _colour_prop(button, False)
    if target is None and slot is None:
        _diag(("target", _ptr(button), _ptr(view)),
              "%s has no colour property or setter; %s"
              % (_class_name(button), _describe(button)))
        return None
    return {"view": view, "button": button, "target": target, "slot": slot}


def _cache(found):
    """Store a discovered target and describe it once per distinct target."""
    state = _STATE
    view = found["view"]
    button = found["button"]
    target = found["target"]
    slot = found["slot"]
    sig = (_ptr(view), _ptr(button),
           _ptr(target["widget"]) if target else 0,
           target["index"] if target else -1,
           target["kind"] if target else "",
           _ptr(slot["widget"]) if slot else 0,
           _method_signature(slot["method"]) if slot else "")
    state["view"] = view
    state["button"] = button
    state["target"] = target
    state["slot"] = slot
    state["diag"] = None
    _hold(view, button,
          target["widget"] if target is not None else None,
          slot["widget"] if slot is not None else None)
    if state.get("sig") != sig:
        state["sig"] = sig
        state["ok"] = None
        state["write_fail"] = None
    return sig


def _read_colour(target):
    """The current colour stored in a target."""
    if target is None or not _alive(target.get("widget")):
        return None
    widget = target["widget"]
    kind = target["kind"]
    if kind in ("qcolor", "variant"):
        try:
            color = _as_colour(target["prop"].read(widget))
        except Exception:
            color = None
        if color is not None:
            return color
        try:
            return _as_colour(widget.property(target["name"]))
        except Exception:
            return None
    values = _raw_values(target)
    if values is None:
        return None
    try:
        return QtGui.QColor.fromRgbF(
            max(0.0, min(1.0, values[0])),
            max(0.0, min(1.0, values[1])),
            max(0.0, min(1.0, values[2])))
    except Exception:
        return None


def _write_target(target, color):
    """Write a colour into a discovered property."""
    if target is None or not _alive(target.get("widget")):
        return False
    widget = target["widget"]
    kind = target["kind"]
    qcolor = QtGui.QColor(color)
    if kind in ("qcolor", "variant"):
        try:
            if target["prop"].write(widget, qcolor):
                return True
        except Exception:
            pass
        try:
            widget.setProperty(target["name"], qcolor)
            return True
        except Exception:
            _log_exc("live: property set")
            return False
    values = [qcolor.redF(), qcolor.greenF(), qcolor.blueF()]
    if kind == "rgb4":
        values.append(1.0)
    if kind in ("rgb3", "rgb4"):
        values = _linear(values[:3]) + values[3:]
    return _raw_write_target(target, values)


def _invoke_slot(slot, color):
    """Write a colour through a discovered setter method."""
    if slot is None or not _alive(slot.get("widget")):
        return False
    widget = slot["widget"]
    kind = slot["kind"]
    qcolor = QtGui.QColor(color)
    values = [qcolor.redF(), qcolor.greenF(), qcolor.blueF()]
    if kind == "rgb4":
        values.append(1.0)
    if kind in ("rgb3", "rgb4"):
        values = _linear(values[:3]) + values[3:]
    if kind in ("qcolor", "variant"):
        try:
            getattr(widget, slot["name"])(qcolor)
            return True
        except Exception:
            pass
    return _raw_invoke_method(widget, slot["method"], values,
                              _method_kinds(slot["method"]))


def _verify(seq, color, target, button):
    """Check the written value and log how the paint tool received it."""
    state = _STATE
    if seq != state.get("seq"):
        return
    try:
        name = color.name().upper()
        if target is None or not _alive(target.get("widget")):
            _diag(("verify-none", state.get("sig")),
                  "Base Color %s sent (no read-back)" % name)
            return
        read = _read_colour(target)
        if read is None:
            _diag(("verify-none", state.get("sig")),
                  "Base Color %s sent (no read-back)" % name)
            return
        rgb = [read.redF(), read.greenF(), read.blueF()]
        wanted = [color.redF(), color.greenF(), color.blueF()]
        if _close(rgb, wanted):
            if state.get("ok") != state.get("sig"):
                state["ok"] = state.get("sig")
                _log("live: Base Color %s applied" % name)
            return
        if _close(rgb, _linear(wanted)):
            if state.get("ok") != state.get("sig"):
                state["ok"] = state.get("sig")
                _log("live: Base Color %s applied (stored linear)" % name)
            return
        _diag(("verify", state.get("sig")),
              "Base Color did not take (%s, read %r); %s"
              % (name, rgb, _describe(button, target)))
        _drop_cache()
    except Exception:
        _log_exc("live: verify")


def _drop_cache():
    """Forget the cached Base Color target."""
    state = _STATE
    state["view"] = None
    state["button"] = None
    state["target"] = None
    state["slot"] = None


def _cached_ok():
    """True while every cached target widget is still alive."""
    state = _STATE
    target = state.get("target")
    slot = state.get("slot")
    if target is None and slot is None:
        return False
    widgets = [state.get("view"), state.get("button")]
    if target is not None:
        widgets.append(target["widget"])
    if slot is not None:
        widgets.append(slot["widget"])
    for widget in widgets:
        if widget is not None and not _alive(widget):
            return False
    return True


def prepare():
    """Detect the Base Color target once and keep it for fast writes."""
    try:
        if _cached_ok():
            return True
        found = _discover()
        if found is None:
            return False
        _cache(found)
        return True
    except Exception:
        _log_exc("live: prepare")
        return False


def refresh():
    """Drop cached widgets so the next apply rediscovers the active tool."""
    _drop_cache()
    _STATE["diag"] = None


def _apply(seq):
    """Write the queued colour through the cached Base Color target."""
    state = _STATE
    if seq != state.get("seq"):
        return
    color = state.get("color")
    if not isinstance(color, QtGui.QColor) or not color.isValid():
        return
    try:
        if not _cached_ok():
            _drop_cache()
            found = _discover()
            if found is None:
                if state.get("retried") != seq:
                    state["retried"] = seq
                    QtCore.QTimer.singleShot(160, lambda: _apply(seq))
                return
            _cache(found)
        target = state.get("target")
        slot = state.get("slot")
        written = False
        if target is not None and target["writable"]:
            written = _write_target(target, color)
        elif slot is not None:
            written = _invoke_slot(slot, color)
        elif target is not None:
            written = _write_target(target, color)
        if written:
            state["diag"] = None
            state["write_fail"] = None
            button = state.get("button")
            QtCore.QTimer.singleShot(
                90, lambda: _verify(seq, color, target, button))
            return
        button = state.get("button")
        sig = state.get("sig")
        _drop_cache()
        if state.get("write_fail") != sig:
            state["write_fail"] = sig
            _log("live: could not write Base Color; %s"
                 % (_describe(button) if button is not None else "-"))
    except Exception:
        _log_exc("live: apply")


def apply_color(color):
    """Apply a picked colour to the active paint tool's Base Color."""
    try:
        color = QtGui.QColor(color)
    except Exception:
        return
    if not color.isValid():
        return
    state = _STATE
    state["seq"] = int(state.get("seq") or 0) + 1
    state["color"] = color
    QtCore.QTimer.singleShot(0, lambda seq=state["seq"]: _apply(seq))
