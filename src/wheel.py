"""Hue-ring colour wheel with a saturation/value triangle and HSB sliders."""
from __future__ import annotations

import math

try:
    from .common import _qt
except ImportError:
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()

TAU = math.pi * 2.0
ROW_H = 13
ROW_GAP = 1
PANEL_MARGIN = 3
FIELD_W = 26


def hsv_color(hue, saturation, value):
    """A QColor from hue 0..360 and saturation/value 0..100."""
    hue = (float(hue) % 360.0) / 360.0
    saturation = max(0.0, min(1.0, float(saturation) / 100.0))
    value = max(0.0, min(1.0, float(value) / 100.0))
    color = QtGui.QColor.fromHsvF(hue, saturation, value)
    if not color.isValid():
        return QtGui.QColor(0, 0, 0)
    return color


def color_hsv(color):
    """Hue 0..360, saturation 0..100 and value 0..100 of a QColor."""
    color = QtGui.QColor(color)
    hue = color.hsvHueF()
    if hue < 0.0:
        hue = 0.0
    return (hue * 360.0, color.hsvSaturationF() * 100.0,
            color.valueF() * 100.0)


def _foot(point, a, b):
    """The perpendicular foot of point on the line through a and b."""
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    denom = dx * dx + dy * dy
    if denom <= 0.0:
        return QtCore.QPointF(a)
    t = ((point.x() - a.x()) * dx + (point.y() - a.y()) * dy) / denom
    return QtCore.QPointF(a.x() + t * dx, a.y() + t * dy)


class ColorWheel(QtWidgets.QWidget):
    """Photocraft-style hue ring around a saturation/value triangle."""

    changed = QtCore.Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._saturation = 100.0
        self._value = 100.0
        self._drag_part = None
        self.setMinimumSize(48, 48)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.setToolTip("Hue ring around a saturation/value triangle")

    def hsv(self):
        """Current hue, saturation and value."""
        return (self._hue, self._saturation, self._value)

    def set_hsv(self, hue, saturation, value):
        """Set the wheel colour without emitting a change."""
        self._hue = float(hue) % 360.0
        self._saturation = max(0.0, min(100.0, float(saturation)))
        self._value = max(0.0, min(100.0, float(value)))
        self.update()

    def _geometry(self):
        center = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)
        outer = max(1.0, min(self.width(), self.height()) / 2.0 - 2.0)
        ring = max(6.0, min(22.0, outer * 0.09))
        ring = min(ring, outer * 0.5)
        return center, outer - ring, outer

    @staticmethod
    def _triangle(center, radius):
        def at(turns):
            angle = turns * TAU
            return QtCore.QPointF(center.x() + math.cos(angle) * radius,
                                  center.y() - math.sin(angle) * radius)
        return [at(0.0), at(1.0 / 3.0), at(2.0 / 3.0)]

    @staticmethod
    def _triangle_point(triangle, saturation, value):
        hue, white, black = triangle
        return QtCore.QPointF(
            black.x() * (1.0 - value)
            + white.x() * value * (1.0 - saturation)
            + hue.x() * value * saturation,
            black.y() * (1.0 - value)
            + white.y() * value * (1.0 - saturation)
            + hue.y() * value * saturation)

    @staticmethod
    def _triangle_sv(triangle, point):
        hue, white, black = triangle
        ax = white.x() - black.x()
        ay = white.y() - black.y()
        cx = hue.x() - white.x()
        cy = hue.y() - white.y()
        dx = point.x() - black.x()
        dy = point.y() - black.y()
        det = ax * cy - ay * cx
        if abs(det) < 1e-6:
            return None
        value = (dx * cy - dy * cx) / det
        saturation = (ax * dy - ay * dx) / det
        if not math.isfinite(value) or not math.isfinite(saturation):
            return None
        value = max(0.0, min(1.0, value))
        saturation = max(0.0, min(value, saturation))
        if value <= 0.0:
            return (0.0, 0.0)
        return (saturation / value, value)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, True)
            center, inner, outer = self._geometry()
            gradient = QtGui.QConicalGradient(center, 0.0)
            for step in range(7):
                gradient.setColorAt(step / 6.0,
                                    hsv_color(step * 60.0, 100.0, 100.0))
            pen = QtGui.QPen(QtGui.QBrush(gradient), outer - inner)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            middle = (inner + outer) / 2.0
            painter.drawEllipse(center, middle, middle)
            triangle = self._triangle(center, max(1.0, inner - 1.0))
            self._paint_triangle(painter, triangle)
            self._paint_knobs(painter, center, inner, outer, triangle)
        finally:
            painter.end()

    def _paint_triangle(self, painter, triangle):
        hue, white, black = triangle
        path = QtGui.QPainterPath()
        path.moveTo(hue)
        path.lineTo(white)
        path.lineTo(black)
        path.closeSubpath()
        painter.save()
        painter.setClipPath(path)
        painter.fillPath(path, QtGui.QColor(0, 0, 0))
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_Plus)
        gradient = QtGui.QLinearGradient(white, _foot(white, hue, black))
        gradient.setColorAt(0.0, QtGui.QColor(255, 255, 255, 255))
        gradient.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
        painter.fillRect(self.rect(), gradient)
        pure = hsv_color(self._hue, 100.0, 100.0)
        gradient = QtGui.QLinearGradient(hue, _foot(hue, white, black))
        gradient.setColorAt(0.0, QtGui.QColor(
            pure.red(), pure.green(), pure.blue(), 255))
        gradient.setColorAt(1.0, QtGui.QColor(
            pure.red(), pure.green(), pure.blue(), 0))
        painter.fillRect(self.rect(), gradient)
        painter.restore()

    def _paint_knobs(self, painter, center, inner, outer, triangle):
        angle = self._hue / 360.0 * TAU
        radius = (inner + outer) / 2.0
        ring_knob = QtCore.QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() - math.sin(angle) * radius)
        sv_knob = self._triangle_point(
            triangle, self._saturation / 100.0, self._value / 100.0)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for knob in (ring_knob, sv_knob):
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5))
            painter.drawEllipse(knob, 4.0, 4.0)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 1.0))
            painter.drawEllipse(knob, 5.0, 5.0)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        center, inner, outer = self._geometry()
        self._drag_part = self._part_at(event.position(), center, inner,
                                        outer)
        self._pick(event.position(), self._drag_part, center, inner)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_part is None:
            return super().mouseMoveEvent(event)
        center, inner, _outer = self._geometry()
        self._pick(event.position(), self._drag_part, center, inner)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_part = None
        super().mouseReleaseEvent(event)

    @staticmethod
    def _part_at(point, center, inner, outer):
        distance = math.hypot(point.x() - center.x(),
                              point.y() - center.y())
        if distance > outer + 7.0:
            return None
        return "hue" if distance >= inner - 2.0 else "sv"

    def _pick(self, point, part, center, inner):
        if part == "hue":
            angle = math.atan2(center.y() - point.y(),
                               point.x() - center.x()) % TAU
            hue = math.degrees(angle)
            if abs(hue - self._hue) > 1e-6:
                self._hue = hue
                self._emit()
            return
        if part != "sv":
            return
        triangle = self._triangle(center, max(1.0, inner - 1.0))
        result = self._triangle_sv(triangle, point)
        if result is None:
            return
        saturation, value = result
        if (abs(saturation - self._saturation / 100.0) > 1e-6
                or abs(value - self._value / 100.0) > 1e-6):
            self._saturation = saturation * 100.0
            self._value = value * 100.0
            self._emit()

    def _emit(self):
        self.update()
        self.changed.emit(self._hue, self._saturation, self._value)


class ChannelSlider(QtWidgets.QWidget):
    """A colour-gradient slider track with a triangular thumb."""

    value_changed = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minimum = 0.0
        self._maximum = 100.0
        self._value = 0.0
        self._stops = []
        self.setFixedHeight(13)
        self.setMinimumWidth(24)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

    def set_range(self, minimum, maximum):
        """Set the value range."""
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self.update()

    def set_stops(self, colors):
        """Set the track colours from left to right."""
        self._stops = [QtGui.QColor(color) for color in colors]
        self.update()

    def value(self):
        """The current value."""
        return self._value

    def set_value(self, value, emit=False):
        """Set the value, optionally announcing the change."""
        value = max(self._minimum, min(self._maximum, float(value)))
        self._value = value
        self.update()
        if emit:
            self.value_changed.emit(value)

    def _bar_rect(self):
        return QtCore.QRectF(3.0, 1.0, max(1.0, self.width() - 6.0), 5.0)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, True)
            bar = self._bar_rect()
            gradient = QtGui.QLinearGradient(bar.topLeft(), bar.topRight())
            count = max(1, len(self._stops) - 1)
            for index, color in enumerate(self._stops):
                gradient.setColorAt(index / count, color)
            if self._stops:
                painter.fillRect(bar, gradient)
            painter.setPen(QtGui.QPen(QtGui.QColor(0x0d, 0x0d, 0x0d), 1.0))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(bar)
            span = self._maximum - self._minimum
            fraction = ((self._value - self._minimum) / span
                        if span > 0.0 else 0.0)
            x = bar.left() + max(0.0, min(1.0, fraction)) * bar.width()
            thumb = QtGui.QPolygonF([
                QtCore.QPointF(x - 4.0, bar.bottom() + 1.0),
                QtCore.QPointF(x + 4.0, bar.bottom() + 1.0),
                QtCore.QPointF(x, bar.bottom() + 5.0)])
            painter.setPen(QtGui.QPen(QtGui.QColor(0x0d, 0x0d, 0x0d), 1.0))
            painter.setBrush(QtGui.QColor(0xe2, 0xe2, 0xe2))
            painter.drawPolygon(thumb)
        finally:
            painter.end()

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        self._set_from_x(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        self._set_from_x(event.position().x())
        event.accept()

    def _set_from_x(self, x):
        bar = self._bar_rect()
        fraction = max(0.0, min(1.0, (x - bar.left()) / bar.width()))
        value = self._minimum + (self._maximum - self._minimum) * fraction
        self.set_value(round(value), emit=True)


class WheelPanel(QtWidgets.QWidget):
    """The colour wheel with H, S and V slider rows beneath it."""

    color_changed = QtCore.Signal(QtGui.QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._saturation = 100.0
        self._value = 100.0
        self._syncing = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN,
                                  PANEL_MARGIN, PANEL_MARGIN)
        layout.setSpacing(ROW_GAP)
        self.wheel = ColorWheel(self)
        self.wheel.changed.connect(self._on_wheel_changed)
        layout.addWidget(self.wheel, 0,
                         QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.sliders = []
        self.fields = []
        for index, (label, maximum) in enumerate(
                (("H", 360.0), ("S", 100.0), ("V", 100.0))):
            row = QtWidgets.QWidget(self)
            row.setFixedHeight(ROW_H)
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            caption = QtWidgets.QLabel(label, row)
            caption.setObjectName("RefCanvasWheelLabel")
            caption.setFixedWidth(9)
            slider = ChannelSlider(row)
            slider.set_range(0.0, maximum)
            slider.value_changed.connect(
                lambda value, i=index: self._on_slider(i, value))
            field = QtWidgets.QLineEdit(row)
            field.setObjectName("RefCanvasWheelField")
            field.setFixedSize(FIELD_W, 13)
            field.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            field.setValidator(QtGui.QIntValidator(0, int(maximum), field))
            field.editingFinished.connect(
                lambda i=index: self._on_field(i))
            row_layout.addWidget(caption)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(field)
            layout.addWidget(row)
            self.sliders.append(slider)
            self.fields.append(field)
        self._sync()

    def set_color(self, color):
        """Show an externally picked colour without emitting a change."""
        hue, saturation, value = color_hsv(color)
        if saturation <= 0.0:
            hue = self._hue
        self._hue = hue
        self._saturation = saturation
        self._value = value
        self._sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rows = 3 * ROW_H + 3 * ROW_GAP
        inside_w = max(48, self.width() - 2 * PANEL_MARGIN)
        inside_h = max(48, self.height() - 2 * PANEL_MARGIN)
        side = max(48, min(inside_w, inside_h - rows))
        self.wheel.setFixedSize(side, side)

    def _on_wheel_changed(self, hue, saturation, value):
        if self._syncing:
            return
        self._hue = hue
        self._saturation = saturation
        self._value = value
        self._sync()
        self._emit()

    def _on_slider(self, index, value):
        if self._syncing:
            return
        self._set_channel(index, value)
        self._sync()
        self._emit()

    def _on_field(self, index):
        field = self.fields[index]
        limit = 360 if index == 0 else 100
        try:
            value = int(field.text())
        except ValueError:
            self._sync()
            return
        self._set_channel(index, max(0, min(limit, value)))
        self._sync()
        self._emit()

    def _set_channel(self, index, value):
        if index == 0:
            self._hue = float(value) % 360.0
        elif index == 1:
            self._saturation = max(0.0, min(100.0, float(value)))
        else:
            self._value = max(0.0, min(100.0, float(value)))

    def _sync(self):
        self._syncing = True
        try:
            self.wheel.set_hsv(self._hue, self._saturation, self._value)
            hue_stops = [hsv_color(step * 30.0, 100.0, 100.0)
                         for step in range(13)]
            saturation_stops = [
                hsv_color(self._hue, step * 100.0 / 12.0, self._value)
                for step in range(13)]
            value_stops = [
                hsv_color(self._hue, self._saturation, step * 100.0 / 12.0)
                for step in range(13)]
            self.sliders[0].set_stops(hue_stops)
            self.sliders[1].set_stops(saturation_stops)
            self.sliders[2].set_stops(value_stops)
            values = (self._hue, self._saturation, self._value)
            for index, (slider, field) in enumerate(
                    zip(self.sliders, self.fields)):
                slider.set_value(values[index])
                if not field.hasFocus():
                    field.setText(str(int(round(values[index]))))
        finally:
            self._syncing = False

    def _emit(self):
        self.color_changed.emit(
            hsv_color(self._hue, self._saturation, self._value))
