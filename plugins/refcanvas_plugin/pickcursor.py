"""Vector eyedropper cursor for Alt colour picking."""
from __future__ import annotations

try:
    from .common import _qt
except ImportError:
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()

_CURSOR = None


def _pick_geo(size):
    """Pipette body and white bore paths for a cursor of the given size."""
    k = size / 32.0
    tip = QtGui.QPainterPath()
    tip.addRoundedRect(QtCore.QRectF(0.0, -1.35 * k, 1.8 * k, 2.7 * k),
                       1.35 * k, 1.35 * k)
    tube = QtGui.QPainterPath()
    tube.addRoundedRect(QtCore.QRectF(1.8 * k, -2.3 * k, 13.0 * k, 4.6 * k),
                        1.0 * k, 1.0 * k)
    neck = QtGui.QPainterPath()
    neck.addRoundedRect(QtCore.QRectF(14.6 * k, -2.55 * k, 1.3 * k, 5.1 * k),
                        0.6 * k, 0.6 * k)
    collar = QtGui.QPainterPath()
    collar.addRoundedRect(
        QtCore.QRectF(15.7 * k, -3.8 * k, 3.4 * k, 7.6 * k),
        0.7 * k, 0.7 * k)
    bulb = QtGui.QPainterPath()
    bulb.addRoundedRect(QtCore.QRectF(19.0 * k, -2.05 * k, 6.0 * k, 4.1 * k),
                        2.05 * k, 2.05 * k)
    body = tip.united(tube).united(neck).united(collar).united(bulb)
    hi = QtGui.QPainterPath()
    hi.addRoundedRect(QtCore.QRectF(2.0 * k, -1.35 * k, 12.7 * k, 2.7 * k),
                      0.7 * k, 0.7 * k)
    hi.addRoundedRect(QtCore.QRectF(1.5 * k, -2.4 * k, 0.6 * k, 2.9 * k),
                      0.3 * k, 0.3 * k)
    tr = QtGui.QTransform()
    tr.translate(2.0 * k, 30.0 * k)
    tr.rotate(-45.0)
    return tr.map(body), tr.map(hi)


def pick_cursor():
    """Return the cached eyedropper cursor with its tip at the hotspot."""
    global _CURSOR
    if _CURSOR is not None:
        return _CURSOR
    try:
        size = 26
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, True)
            k = size / 32.0
            body, hi = _pick_geo(float(size))
            painter.setPen(QtGui.QPen(
                QtGui.QColor(245, 245, 245), 2.4 * k,
                QtCore.Qt.PenStyle.SolidLine,
                QtCore.Qt.PenCapStyle.RoundCap,
                QtCore.Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QtGui.QColor(245, 245, 245))
            painter.drawPath(body)
            painter.setPen(QtGui.QPen(
                QtGui.QColor(15, 15, 15), 0.35 * k,
                QtCore.Qt.PenStyle.SolidLine,
                QtCore.Qt.PenCapStyle.RoundCap,
                QtCore.Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QtGui.QColor(15, 15, 15))
            painter.drawPath(body)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(245, 245, 245))
            painter.drawPath(hi)
        finally:
            painter.end()
        _CURSOR = QtGui.QCursor(pixmap, 2, 24)
    except Exception:
        _CURSOR = QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor)
    return _CURSOR
