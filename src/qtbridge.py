"""Qt5/Qt6 property and signal helpers for the Live ON colour bridge."""
from __future__ import annotations

import ctypes
import os
import struct

try:
    from .common import _log, _log_exc, _qt, _shiboken
except ImportError:
    from common import _log, _log_exc, _qt, _shiboken

QtCore, QtGui, QtWidgets = _qt()
_SHIBOKEN = _shiboken()

_METACALL = None
_METACALL_TRIED = False
_FAULT_CB = {"fn": None}


def set_fault_callback(callback):
    """Register the callback fired when a raw metacall hits a memory fault."""
    _FAULT_CB["fn"] = callback


def _fault(exc):
    """Notify the owner when a raw access raised (access violation / C++ exc).

    Those errors mean the write landed on freed or moving memory - the exact
    condition that hard-crashed Painter before. The owner switches Live OFF
    so no further raw access is attempted this session.
    """
    if not isinstance(exc, OSError):
        return
    callback = _FAULT_CB["fn"]
    if callback is None:
        return
    try:
        callback()
    except Exception:
        pass
_INVOKE = 0
_READ = 1
_WRITE = 2
_PROCS = {}
_MANUAL = {}
_CTOR_RVA = 0x8afa30
_DTOR_RVA = 0x8afa90
_CTOR_SIG = bytes.fromhex("40534883ec20488bd94883c1104885d274")
_DTOR_SIG = bytes.fromhex("4883c110e9")


def _alive(widget):
    """True while a Qt wrapper still points at a live widget."""
    if widget is None:
        return False
    try:
        widget.metaObject()
    except Exception:
        return False
    if _SHIBOKEN is not None:
        try:
            return bool(_SHIBOKEN.isValid(widget))
        except Exception:
            return True
    return True


def _cpp_ptr(widget):
    """C++ address of a live widget, or 0 when unavailable."""
    if _SHIBOKEN is None or not _alive(widget):
        return 0
    try:
        return int(_SHIBOKEN.getCppPointer(widget)[0])
    except Exception:
        return 0


def _ptr(widget):
    """Stable identity for a Qt widget."""
    pointer = _cpp_ptr(widget)
    if pointer:
        return pointer
    try:
        return id(widget)
    except Exception:
        return 0


def _class_name(widget):
    """Qt class name of a widget."""
    try:
        return str(widget.metaObject().className() or "")
    except Exception:
        return ""


def _walk(root):
    """Widget descendants of root in child order."""
    out = []

    def rec(widget):
        try:
            children = widget.children()
        except Exception:
            return
        for child in children:
            try:
                if not child.isWidgetType():
                    continue
            except Exception:
                continue
            out.append(child)
            rec(child)

    rec(root)
    return out


def _text(value):
    """Decode a Qt meta name or QByteArray to plain text."""
    if isinstance(value, str):
        return value
    for read in (lambda item: item.data(), bytes):
        try:
            raw = read(value)
        except Exception:
            continue
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw).decode("utf-8", "replace")
    try:
        return str(value or "")
    except Exception:
        return ""


def _prop_rows(widget):
    """(index, name, QMetaProperty) for every property on a widget."""
    rows = []
    if not _alive(widget):
        return rows
    try:
        meta = widget.metaObject()
        for index in range(meta.propertyCount()):
            prop = meta.property(index)
            rows.append((index, _text(prop.name()), prop))
    except Exception:
        _log_exc("live: properties")
    return rows


def _prop_size(prop):
    """Byte size of a property's value type."""
    if prop is None:
        return 12
    try:
        size = int(prop.metaType().sizeOf())
        if size >= 12:
            return size
    except Exception:
        pass
    size = _meta_size(prop)
    if size >= 12:
        return size
    try:
        meta_type = getattr(QtCore, "QMetaType", None)
        if meta_type is not None:
            size = int(meta_type.sizeOf(_type_id(prop)))
            if size >= 12:
                return size
    except Exception:
        pass
    name = (_text(prop.typeName()).replace("const", "").replace("&", "")
            .replace(" ", "").lower())
    if "qcolor" in name:
        return 16
    if "4,1" in name or "vector4" in name or "float4" in name \
            or "color4" in name or "rgba" in name:
        return 16
    if "3,1" in name or "vector3" in name or "float3" in name \
            or "color3" in name or "rgb" in name:
        return 12
    return 12


def _type_id(prop):
    """Metatype id of a property's value type, or 0."""
    if prop is None:
        return 0
    for name in ("userType", "typeId"):
        try:
            value = getattr(prop, name)
            type_id = int(value() if callable(value) else value)
            if type_id > 0:
                return type_id
        except Exception:
            continue
    try:
        type_proc = _qt_proc(
            b"?type@QMetaType@@SAHPEBD@Z",
            ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_char_p))
        if type_proc is not None:
            type_id = int(type_proc(_text(prop.typeName()).encode("utf-8")))
            return type_id if type_id > 0 else 0
    except Exception:
        pass
    return 0


def _size_of(type_id):
    """Size of a metatype id, or 0."""
    if not type_id:
        return 0
    size_proc = _qt_proc(
        b"?sizeOf@QMetaType@@SAHH@Z",
        ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int))
    if size_proc is None:
        return 0
    try:
        size = int(size_proc(type_id))
        return size if size > 0 else 0
    except Exception:
        return 0


def _meta_size(prop):
    """Size of a property's value type from Qt's metatype registry."""
    return _size_of(_type_id(prop))


def _qt5():
    """True when Painter runs on Qt 5."""
    try:
        return str(QtCore.qVersion() or "").startswith("5.")
    except Exception:
        return False


def _exe_base():
    """Base address of the Painter process executable."""
    if not hasattr(ctypes, "WinDLL"):
        return 0
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        return int(kernel32.GetModuleHandleW(None) or 0)
    except Exception:
        return 0


def _new_manual(prop):
    """Construct Alg::EditColor3 with Painter's own constructor, or 0."""
    base = _exe_base()
    if not base:
        return 0
    try:
        sig = ctypes.string_at(base + _CTOR_RVA, len(_CTOR_SIG))
    except Exception:
        return 0
    if sig != _CTOR_SIG:
        return 0
    size = max(88, _prop_size(prop) if prop is not None else 0)
    try:
        buffer = ctypes.create_string_buffer(size)
        ctor = ctypes.WINFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
                base + _CTOR_RVA)
        address = ctypes.addressof(buffer)
        ctor(ctypes.c_void_p(address), None)
    except Exception:
        _log_exc("live: value construct")
        return 0
    _MANUAL[address] = buffer
    return address


def _drop_manual(address):
    """Destroy a value built by _new_manual."""
    buffer = _MANUAL.pop(int(address), None)
    if buffer is None:
        return
    base = _exe_base()
    if not base:
        return
    try:
        sig = ctypes.string_at(base + _DTOR_RVA, len(_DTOR_SIG))
    except Exception:
        return
    if sig != _DTOR_SIG:
        return
    dtor = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)(base + _DTOR_RVA)
    try:
        dtor(ctypes.c_void_p(int(address)))
    except Exception:
        _log_exc("live: value destroy")


def _new_value(target):
    """Construct a Qt5 property value directly, or 0."""
    if not _qt5():
        return 0
    return _new_manual(target.get("prop"))


def _drop_value(value):
    """Destroy a value made by _new_value."""
    if value:
        _drop_manual(value)


def _load_value(target, value):
    """Copy the current property value into a constructed Qt5 value."""
    proc = _metacall_proc()
    ptr = _cpp_ptr(target["widget"])
    index = int(target["index"])
    if proc is None or not ptr or not value or index < 0:
        return False
    try:
        argv = (ctypes.c_void_p * 1)(ctypes.c_void_p(value))
        proc(ptr, _READ, index, argv)
        return True
    except Exception:
        _log_exc("live: property read")
        return False


def _colour_kind(type_name, prop=None):
    """Colour storage kind for a Qt type name, or None."""
    low = _text(type_name).replace("const", "").replace("&", "") \
        .replace(" ", "").lower()
    if not low:
        return None
    if low.endswith("qcolor") or low.endswith("qcolor*"):
        return "qcolor"
    if "qvariant" in low:
        return "variant"
    if "globalcolor" in low or "colorspace" in low or "colormap" in low:
        return None
    if "matrix<float,4,1" in low or "matrix<float,4" in low \
            or "vector4f" in low:
        return "rgb4"
    if "matrix<float,3,1" in low or "matrix<float,3" in low \
            or "vector3f" in low:
        return "rgb3"
    if "editcolor4" in low:
        return "rgb4"
    if "editcolor3" in low:
        return "rgb3"
    if "editcolor" in low:
        return "rgb4" if _prop_size(prop) >= 16 else "rgb3"
    if "color" in low or "colour" in low:
        return "rgb4" if _prop_size(prop) >= 16 else "rgb3"
    if "float3" in low or "vector3" in low or "vec3" in low:
        return "rgb3"
    if "float4" in low or "vector4" in low or "vec4" in low:
        return "rgb4"
    return None


def _method_index(method):
    """Qt5/Qt6 method index of a QMetaMethod."""
    for name in ("methodIndex", "index"):
        try:
            value = getattr(method, name)
            return int(value() if callable(value) else value)
        except Exception:
            continue
    return -1


def _method_signature(method):
    """Readable signature of a QMetaMethod on Qt5 or Qt6."""
    for name in ("methodSignature", "signature"):
        try:
            return _text(getattr(method, name)())
        except Exception:
            continue
    try:
        return "%s(%s)" % (_text(method.name()), ", ".join(
            _text(kind) for kind in method.parameterTypes()))
    except Exception:
        return "?"


def _method_type(method):
    """Qt method kind: 0 method, 1 signal, 2 slot."""
    try:
        value = method.methodType()
    except Exception:
        return -1
    try:
        return int(value)
    except Exception:
        pass
    try:
        return int(value.value)
    except Exception:
        return -1


def _method_kinds(method):
    """Decoded parameter type names of a QMetaMethod."""
    try:
        return [_text(kind) for kind in method.parameterTypes()]
    except Exception:
        return []


def _colour_methods(widget, names):
    """Methods on a widget whose lower-case names are in names."""
    out = []
    if not _alive(widget):
        return out
    wanted = set(name.lower() for name in names)
    try:
        meta = widget.metaObject()
        for index in range(meta.methodCount()):
            method = meta.method(index)
            if _text(method.name()).lower() in wanted:
                out.append(method)
    except Exception:
        _log_exc("live: methods")
    return out


def _process_modules():
    """Paths of modules loaded in the Painter process."""
    out = []
    if not hasattr(ctypes, "WinDLL"):
        return out
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel32.GetCurrentProcess()
        enum = None
        for lib, name in (("kernel32", "K32EnumProcessModules"),
                          ("psapi", "EnumProcessModules")):
            try:
                enum = getattr(ctypes.WinDLL(lib, use_last_error=True), name)
                break
            except Exception:
                enum = None
        if enum is None:
            return out
        enum.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                         ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        enum.restype = ctypes.c_int
        size = 1024
        handles = None
        count = 0
        while size <= 32768:
            handles = (ctypes.c_void_p * size)()
            needed = ctypes.c_uint32(0)
            if not enum(process, handles, ctypes.sizeof(handles),
                        ctypes.byref(needed)):
                handles = None
                break
            count = int(needed.value) // ctypes.sizeof(ctypes.c_void_p)
            if count < size:
                break
            size *= 2
        if handles is None or count <= 0:
            return out
        get_name = kernel32.GetModuleFileNameW
        get_name.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                             ctypes.c_uint32]
        get_name.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(1024)
        for handle in handles[:count]:
            if get_name(handle, buffer, 1024):
                out.append(buffer.value)
    except Exception:
        _log_exc("live: module list")
    return out


def _core_handles():
    """Handles of the Qt core libraries loaded by Painter."""
    out = []
    try:
        if not hasattr(ctypes, "WinDLL"):
            return out
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        for name in ("Qt6Core.dll", "Qt6Core6.dll", "Qt6Cored.dll",
                     "Qt5Core.dll", "Qt5Core5.dll", "Qt5Cored.dll"):
            handle = kernel32.GetModuleHandleW(name)
            if handle and all(handle != item[0] for item in out):
                out.append((handle, name))
        if not out:
            for path in _process_modules():
                base = os.path.basename(path)
                low = base.lower()
                if not (low.startswith("qt5core")
                        or low.startswith("qt6core")):
                    continue
                handle = (kernel32.GetModuleHandleW(path)
                          or kernel32.GetModuleHandleW(base))
                if handle and all(handle != item[0] for item in out):
                    out.append((handle, base))
    except Exception:
        _log_exc("live: core modules")
    return out


def _core_export(symbol):
    """Address and module name of a Qt core export."""
    try:
        if not hasattr(ctypes, "WinDLL"):
            return None, ""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetProcAddress.restype = ctypes.c_void_p
        kernel32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        for module, name in _core_handles():
            address = kernel32.GetProcAddress(module, symbol)
            if address:
                return address, name
    except Exception:
        _log_exc("live: core export")
    return None, ""


def _qt_proc(symbol, prototype):
    """Cached ctypes callable for a Qt core symbol."""
    if symbol in _PROCS:
        return _PROCS[symbol]
    address, _ = _core_export(symbol)
    _PROCS[symbol] = prototype(address) if address else None
    return _PROCS[symbol]


def _metacall_proc():
    """QMetaObject::metacall from the Qt core library Painter loaded."""
    global _METACALL, _METACALL_TRIED
    if _METACALL_TRIED:
        return _METACALL
    _METACALL_TRIED = True
    symbol = b"?metacall@QMetaObject@@SAHPEAVQObject@@W4Call@1@HPEAPEAX@Z"
    address, _ = _core_export(symbol)
    if address:
        prototype = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p))
        _METACALL = prototype(address)
        return _METACALL
    _log("live: QMetaObject::metacall not found")
    return None


def _finite(values):
    """True when numbers look like plausible colour fractions."""
    try:
        return all(value == value and abs(value) <= 64.0 for value in values)
    except Exception:
        return False


def _raw_values(target):
    """Read three colour fractions through QMetaObject::metacall."""
    proc = _metacall_proc()
    ptr = _cpp_ptr(target["widget"])
    index = int(target["index"])
    if proc is None or not ptr or index < 0:
        return None
    value = _new_value(target)
    if value:
        try:
            if not _load_value(target, value):
                return None
            values = list(struct.unpack("<3f", ctypes.string_at(value, 12)))
            return values if _finite(values) else None
        finally:
            _drop_value(value)
    if _qt5():
        return None
    buf = ctypes.create_string_buffer(
        max(64, _prop_size(target["prop"]) + 16))
    argv = (ctypes.c_void_p * 1)(ctypes.cast(buf, ctypes.c_void_p))
    try:
        proc(ptr, _READ, index, argv)
        values = list(struct.unpack_from("<3f", buf, 0))
    except Exception as exc:
        _log_exc("live: property read")
        _fault(exc)
        return None
    return values if _finite(values) else None


def _raw_write_target(target, values):
    """Write colour fractions through QMetaObject::metacall."""
    proc = _metacall_proc()
    ptr = _cpp_ptr(target["widget"])
    index = int(target["index"])
    if proc is None or not ptr or index < 0:
        return False
    count = 4 if len(values) >= 4 else 3
    value = _new_value(target)
    if value:
        try:
            if not _load_value(target, value):
                _drop_value(value)
                value = _new_value(target)
                if not value:
                    return False
            floats = ctypes.cast(ctypes.c_void_p(value),
                                 ctypes.POINTER(ctypes.c_float))
            for offset in range(count):
                floats[offset] = float(values[offset])
            argv = (ctypes.c_void_p * 1)(ctypes.c_void_p(value))
            proc(ptr, _WRITE, index, argv)
            return True
        except Exception as exc:
            _log_exc("live: property write")
            _fault(exc)
            return False
        finally:
            _drop_value(value)
    if _qt5():
        return False
    buf = ctypes.create_string_buffer(
        max(64, _prop_size(target["prop"]) + 16))
    try:
        struct.pack_into("<%df" % count, buf, 0, *values[:count])
    except Exception:
        return False
    argv = (ctypes.c_void_p * 1)(ctypes.cast(buf, ctypes.c_void_p))
    try:
        proc(ptr, _WRITE, index, argv)
        return True
    except Exception as exc:
        _log_exc("live: property write")
        _fault(exc)
        return False


def _float_kind(name):
    """True for Qt floating point parameter type names."""
    return _text(name).strip().lower() in (
        "float", "double", "qreal", "float32", "float64")


def _raw_call_kind(kinds):
    """Argument packing for a safe metacall invoke, or None for custom types."""
    if not kinds:
        return "none"
    if len(kinds) == 1:
        low = (_text(kinds[0]).replace("const", "").replace("&", "")
               .replace(" ", "").lower())
        if low == "qcolor":
            return "qcolor"
        return None
    if len(kinds) == 3 and all(_float_kind(kind) for kind in kinds):
        return "floats"
    return None


def _raw_invoke_method(widget, method, values, kinds):
    """Invoke one Qt method with arguments packed by hand."""
    pack = _raw_call_kind(kinds)
    if pack is None:
        return False
    proc = _metacall_proc()
    ptr = _cpp_ptr(widget)
    index = _method_index(method)
    if proc is None or not ptr or index < 0:
        return False
    keep = []
    try:
        if pack == "none":
            argv = (ctypes.c_void_p * 1)(None)
        elif pack == "qcolor":
            color = QtGui.QColor.fromRgbF(*values[:3])
            keep.append(color)
            if _SHIBOKEN is None:
                return False
            pointer = int(_SHIBOKEN.getCppPointer(color)[0])
            if not pointer:
                return False
            argv = (ctypes.c_void_p * 2)(None, ctypes.c_void_p(pointer))
        else:
            cells = []
            pointers = []
            for kind, value in zip(kinds, values[:3]):
                cell = (ctypes.c_double(value) if kind.strip().lower()
                        in ("double", "qreal", "float64")
                        else ctypes.c_float(value))
                cells.append(cell)
                pointers.append(ctypes.cast(ctypes.pointer(cell),
                                            ctypes.c_void_p))
            keep.extend(cells)
            keep.extend(pointers)
            argv = (ctypes.c_void_p * 4)(None, *pointers)
        proc(ptr, _INVOKE, index, argv)
        return True
    except Exception as exc:
        _log_exc("live: method invoke")
        _fault(exc)
        return False


def _python_emit(widget, name, args):
    """Emit a Qt signal through its Python wrapper."""
    try:
        signal = getattr(widget, name)
        signal.emit(*args)
        return True
    except Exception:
        return False


def _emit_one(widget, method, color):
    """Invoke one colour-change signal with matching arguments."""
    name = _text(method.name())
    kinds = _method_kinds(method)
    values = [color.redF(), color.greenF(), color.blueF()]
    if not kinds:
        return _python_emit(widget, name, ())
    if len(kinds) == 1:
        kind = _colour_kind(kinds[0])
        if kind in ("qcolor", "variant"):
            if _python_emit(widget, name, (QtGui.QColor(color),)):
                return True
            if kind == "qcolor":
                return _raw_invoke_method(widget, method, values, kinds)
        return False
    if len(kinds) == 3 and all(_float_kind(kind) for kind in kinds):
        return _raw_invoke_method(widget, method, values, kinds)
    return False


def _as_colour(value):
    """A QColor from a QColor, QVariant or convertible value."""
    if isinstance(value, QtGui.QColor):
        return value if value.isValid() else None
    for name in ("value", "toColor"):
        try:
            inner = getattr(value, name)
            inner = inner() if callable(inner) else inner
            if isinstance(inner, QtGui.QColor) and inner.isValid():
                return inner
        except Exception:
            pass
    try:
        color = QtGui.QColor(value)
        return color if color.isValid() else None
    except Exception:
        return None


def _linear(values):
    """Fractions converted from sRGB to linear light."""
    out = []
    for value in values:
        value = max(0.0, min(1.0, float(value)))
        out.append(value / 12.92 if value <= 0.04045
                   else ((value + 0.055) / 1.055) ** 2.4)
    return out


def _close(left, right):
    """True when two colour fraction triples agree within rounding."""
    try:
        return all(abs(float(a) - float(b)) <= 0.025
                   for a, b in zip(left, right))
    except Exception:
        return False
