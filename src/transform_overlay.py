"""Transform box and warp mesh overlay painting."""
from __future__ import annotations

try:
    from .common import _log_exc, _qt
except ImportError:
    from common import _log_exc, _qt

QtCore, QtGui, QtWidgets = _qt()

HANDLE_PX = 7.0


def draw_overlay(session, painter):
    """Paint the active session box or warp mesh over the canvas."""
    if not session.active:
        return
    try:
        rect = session.canvas.image_rect()
        z = session.canvas.zoom()

        def sp(q):
            return QtCore.QPointF(rect.left() + q[0] * z,
                                  rect.top() + q[1] * z)
        painter.save()
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, True)
            if session.warp is not None:
                _warp(session, painter, sp)
            else:
                _box(session, painter, sp)
        finally:
            painter.restore()
    except Exception:
        _log_exc("transform overlay")


def _box(session, painter, sp):
    poly = QtGui.QPolygonF([sp(q) for q in session.quad])
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 190), 2.6))
    painter.drawPolygon(poly)
    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.1))
    painter.drawPolygon(poly)
    white = QtGui.QColor(255, 255, 255)
    black = QtGui.QColor(0, 0, 0)
    half = HANDLE_PX * 0.5
    pts = list(session.quad)
    for i in range(4):
        a = session.quad[i]
        b = session.quad[(i + 1) % 4]
        pts.append(((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5))
    for q in pts:
        c = sp(q)
        box = QtCore.QRectF(c.x() - half, c.y() - half,
                            HANDLE_PX, HANDLE_PX)
        painter.setBrush(white)
        painter.setPen(QtGui.QPen(black, 1.0))
        painter.drawRect(box)
    c = sp(session.pivot)
    painter.setBrush(white)
    painter.setPen(QtGui.QPen(black, 1.0))
    painter.drawEllipse(c, 4.2, 4.2)
    painter.drawLine(QtCore.QPointF(c.x() - 6.5, c.y()),
                     QtCore.QPointF(c.x() + 6.5, c.y()))
    painter.drawLine(QtCore.QPointF(c.x(), c.y() - 6.5),
                     QtCore.QPointF(c.x(), c.y() + 6.5))


def _warp(session, painter, sp):
    m = session.warp
    cols = len(m.us) - 1
    rows = len(m.vs) - 1
    black = QtGui.QColor(0, 0, 0, 185)
    white = QtGui.QColor(255, 255, 255)

    def line(pts, wb=2.2, ww=1.05):
        poly = QtGui.QPolygonF([sp(q) for q in pts])
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(black, wb))
        painter.drawPolyline(poly)
        painter.setPen(QtGui.QPen(white, ww))
        painter.drawPolyline(poly)
    steps = 36
    for pi in range(cols + 1):
        u = m.us[pi]
        line([m.eval(u, j / float(steps)) for j in range(steps + 1)])
    for pj in range(rows + 1):
        v = m.vs[pj]
        line([m.eval(j / float(steps), v) for j in range(steps + 1)])
    if cols == 1 and rows == 1:
        dash = QtGui.QColor(255, 255, 255, 120)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(dash, 0.9,
                                  QtCore.Qt.PenStyle.DashLine))
        for f in (1.0 / 3.0, 2.0 / 3.0):
            painter.drawPolyline(QtGui.QPolygonF(
                [sp(m.eval(f, j / float(steps)))
                 for j in range(steps + 1)]))
            painter.drawPolyline(QtGui.QPolygonF(
                [sp(m.eval(j / float(steps), f))
                 for j in range(steps + 1)]))
    nx = m.nx()
    for idx, q in enumerate(m.points):
        i = idx % nx
        j = idx // nx
        if i % 3 != 0 and j % 3 != 0:
            continue
        c = sp(q)
        if i % 3 == 0 and j % 3 == 0:
            half = 2.8
            painter.setBrush(white)
            painter.setPen(QtGui.QPen(black, 1.0))
            painter.drawRect(QtCore.QRectF(
                c.x() - half, c.y() - half, half * 2.0, half * 2.0))
        else:
            painter.setBrush(white)
            painter.setPen(QtGui.QPen(black, 1.0))
            painter.drawEllipse(c, 2.5, 2.5)
