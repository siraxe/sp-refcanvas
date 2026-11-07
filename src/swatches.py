"""Two-row colour swatch slot grid for REFCANVAS."""
from __future__ import annotations

try:
    from .common import _qt
except ImportError:
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()


class SwatchGrid(QtWidgets.QWidget):
    """Two rows of ten rectangular slots holding saved colours."""

    COLUMNS = 10
    ROWS = 2
    GAP = 4
    SLOT_H = 13

    color_selected = QtCore.Signal(QtGui.QColor)
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RefCanvasSwatchGrid")
        self._colors = [None] * (self.COLUMNS * self.ROWS)
        self._next = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedHeight(self.ROWS * self.SLOT_H
                            + (self.ROWS - 1) * self.GAP)
        self.setToolTip("Saved swatches; click one to use its colour")

    def colors(self):
        """The stored colours, with None for empty slots."""
        return list(self._colors)

    def next_index(self):
        """The slot used next once the grid is full."""
        return int(self._next)

    def set_colors(self, colors, next_index=0):
        """Load saved swatch colours without notifying."""
        values = []
        for value in list(colors or [])[:len(self._colors)]:
            color = QtGui.QColor(value) if value else QtGui.QColor()
            values.append(color if color.isValid() else None)
        values.extend([None] * (len(self._colors) - len(values)))
        self._colors = values
        try:
            self._next = int(next_index) % len(self._colors)
        except Exception:
            self._next = 0
        if None in values:
            self._next = values.index(None)
        self.update()

    def add_color(self, color):
        """Store a colour in the next slot, wrapping to the start when full."""
        color = QtGui.QColor(color)
        if not color.isValid():
            return
        if None in self._colors:
            index = self._colors.index(None)
        else:
            index = self._next
        self._colors[index] = color
        self._next = (index + 1) % len(self._colors)
        self.update()
        self.changed.emit()

    def clear_colors(self):
        """Empty every slot."""
        self._colors = [None] * len(self._colors)
        self._next = 0
        self._hover = -1
        self.update()
        self.changed.emit()

    def _slot_rect(self, index):
        row, column = divmod(index, self.COLUMNS)
        width = max(1.0, (self.width()
                          - (self.COLUMNS - 1) * self.GAP)
                    / float(self.COLUMNS))
        left = column * (width + self.GAP)
        top = row * (self.SLOT_H + self.GAP)
        return QtCore.QRectF(left, top, width, float(self.SLOT_H))

    def _index_at(self, pos):
        point = QtCore.QPointF(pos)
        for index in range(len(self._colors)):
            if self._slot_rect(index).contains(point):
                return index
        return -1

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, False)
            for index, color in enumerate(self._colors):
                rect = self._slot_rect(index).adjusted(
                    0.5, 0.5, -0.5, -0.5)
                if color is None:
                    painter.fillRect(rect, QtGui.QColor(0x2b, 0x2b, 0x2b))
                else:
                    painter.fillRect(rect, color)
                painter.setPen(QtGui.QPen(QtGui.QColor(0x0d, 0x0d, 0x0d), 1.0))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
        finally:
            painter.end()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            index = self._index_at(event.position())
            if index >= 0 and self._colors[index] is not None:
                self.color_selected.emit(QtGui.QColor(self._colors[index]))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        if index >= 0 and self._colors[index] is None:
            index = -1
        if index != self._hover:
            self._hover = index
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor
                           if index >= 0
                           else QtCore.Qt.CursorShape.ArrowCursor)
            if index >= 0:
                self.setToolTip("%s - click to use"
                                % self._colors[index].name().upper())
            else:
                self.setToolTip("Saved swatches; click one to use its colour")
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover != -1:
            self._hover = -1
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            self.setToolTip("Saved swatches; click one to use its colour")
            self.update()
        super().leaveEvent(event)
