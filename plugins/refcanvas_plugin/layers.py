"""Layer records and the Photoshop-style layer list for REFCANVAS."""
from __future__ import annotations

try:
    from .common import _qt
except ImportError:
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()


class RefLayer:
    """One reference image placed on the collage canvas."""

    def __init__(self, image, name="", path="", x=0.0, y=0.0):
        self.image = QtGui.QImage(image)
        self.name = str(name or "Layer")
        self.path = str(path or "")
        self.x = float(x)
        self.y = float(y)
        self.visible = True

    def bounds(self):
        """Return the layer rectangle in document pixels."""
        return QtCore.QRectF(self.x, self.y,
                             float(self.image.width()),
                             float(self.image.height()))

    def contains(self, x, y):
        """True when a visible layer covers a document point."""
        if self.image.isNull() or not self.visible:
            return False
        return self.bounds().contains(QtCore.QPointF(x, y))

    def set_image(self, image):
        """Replace the layer pixels after a transform is applied."""
        self.image = QtGui.QImage(image)


class LayerRow(QtWidgets.QWidget):
    """One painted layer row with eye, thumbnail, name and drag reorder."""

    def __init__(self, panel, layer, index):
        super().__init__(panel.host())
        self.panel = panel
        self.layer = layer
        self.index = index
        self._arm = None
        self.setFixedHeight(panel.ROW_H)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip("%s - drag to reorder, Delete removes" % layer.name)
        slot = panel.slot_rect()
        inner = slot.adjusted(panel.SLOT_PAD, panel.SLOT_PAD,
                              -panel.SLOT_PAD, -panel.SLOT_PAD)
        self._thumb = QtGui.QPixmap()
        if not layer.image.isNull():
            self._thumb = QtGui.QPixmap.fromImage(layer.image).scaled(
                inner.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)

    def eye_zone(self):
        """The click strip that toggles visibility."""
        return QtCore.QRect(0, 0, self.panel.EYE_W, self.height())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            selected = self.panel.canvas.selected_layer() is self.layer
            row = (QtGui.QColor(0x50, 0x50, 0x50) if selected
                   else QtGui.QColor(0x3b, 0x3b, 0x3b))
            painter.fillRect(self.rect(), row)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, True)
            self._paint_eye(painter)
            self._paint_thumb(painter, selected)
            self._paint_name(painter)
            self._paint_drag_line(painter)
        finally:
            painter.end()

    def _paint_eye(self, painter):
        zone = self.panel.EYE_W
        rect = QtCore.QRect((zone - 14) // 2, (self.height() - 14) // 2,
                            14, 14)
        vis = self.layer.visible
        color = (QtGui.QColor(0xd0, 0xd0, 0xd0) if vis
                 else QtGui.QColor(0x6e, 0x6e, 0x6e))
        pen = QtGui.QPen(color, 1.2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        cx = float(rect.center().x())
        cy = float(rect.center().y())
        path = QtGui.QPainterPath()
        path.moveTo(float(rect.left()), cy)
        path.cubicTo(rect.left() + rect.width() * 0.25, rect.top() - 1,
                     rect.right() - rect.width() * 0.25, rect.top() - 1,
                     float(rect.right()), cy)
        path.cubicTo(rect.right() - rect.width() * 0.25, rect.bottom() + 1,
                     rect.left() + rect.width() * 0.25, rect.bottom() + 1,
                     float(rect.left()), cy)
        painter.drawPath(path)
        if vis:
            painter.setBrush(color)
            painter.drawEllipse(QtCore.QRectF(cx - 2.5, cy - 2.5, 5.0, 5.0))
        else:
            painter.drawLine(rect.left() + 1, rect.bottom(),
                             rect.right() - 1, rect.top())

    def _paint_thumb(self, painter, selected):
        slot = self.panel.slot_rect()
        slot.moveTop((self.height() - slot.height()) // 2)
        inner = slot.adjusted(self.panel.SLOT_PAD, self.panel.SLOT_PAD,
                              -self.panel.SLOT_PAD, -self.panel.SLOT_PAD)
        tile = 4
        for y in range(inner.top(), inner.bottom() + 1, tile):
            for x in range(inner.left(), inner.right() + 1, tile):
                on = ((x - inner.left()) // tile
                      + (y - inner.top()) // tile) % 2
                painter.fillRect(
                    QtCore.QRect(x, y, tile, tile),
                    QtGui.QColor(0xbd, 0xbd, 0xbd) if on
                    else QtGui.QColor(0x8e, 0x8e, 0x8e))
        if not self._thumb.isNull():
            x = inner.left() + (inner.width() - self._thumb.width()) // 2
            y = inner.top() + (inner.height() - self._thumb.height()) // 2
            painter.drawPixmap(x, y, self._thumb)
        painter.setPen(QtGui.QPen(QtGui.QColor(0x8f, 0x8f, 0x8f), 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(inner.adjusted(0, 0, -1, -1))
        if selected:
            painter.setPen(QtGui.QPen(QtGui.QColor(0xe8, 0xe8, 0xe8), 1))
            painter.drawRect(slot.adjusted(0, 0, -1, -1))

    def _paint_name(self, painter):
        font = QtGui.QFont(self.font())
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(0xdc, 0xdc, 0xdc)
                       if self.layer.visible
                       else QtGui.QColor(0x8f, 0x8f, 0x8f))
        metrics = QtGui.QFontMetrics(font)
        name = metrics.elidedText(
            self.layer.name, QtCore.Qt.TextElideMode.ElideRight,
            max(10, self.width() - self.panel.name_x(self) - 4))
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        painter.drawText(self.panel.name_x(self), baseline, name)

    def _paint_drag_line(self, painter):
        index = self.panel.drag_index()
        if index is None:
            return
        line = None
        if index == self.index:
            line = QtCore.QRect(0, 0, self.width(), 2)
        elif index == self.panel.row_count() and self.index == (
                self.panel.row_count() - 1):
            line = QtCore.QRect(0, self.height() - 2, self.width(), 2)
        if line is not None:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, False)
            painter.fillRect(line, QtGui.QColor(0x3d, 0x8f, 0xff))

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        if self.eye_zone().contains(event.position().toPoint()):
            self.panel.canvas.set_layer_visible(
                self.layer, not self.layer.visible)
            event.accept()
            return
        self.panel.begin_row_press(self, event.globalPosition().toPoint())
        event.accept()

    def mouseMoveEvent(self, event):
        if self.panel.drag_row() is not self:
            return super().mouseMoveEvent(event)
        self.panel.move_row(event.globalPosition().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.panel.drag_row() is not self:
            return super().mouseReleaseEvent(event)
        self.panel.release_row(self, event.globalPosition().toPoint())
        event.accept()


class LayerPanel(QtWidgets.QScrollArea):
    """Scrollable Photoshop-style layer list bound to a canvas."""

    ROW_H = 30
    ROW_GAP = 2
    EYE_W = 24
    THUMB = 20
    SLOT_PAD = 3
    MAX_ROWS = 3

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setObjectName("RefCanvasLayerArea")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._host = QtWidgets.QWidget()
        self._host.setObjectName("RefCanvasLayerHost")
        self._layout = QtWidgets.QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.ROW_GAP)
        self.setWidget(self._host)
        self.viewport().setAutoFillBackground(False)
        self._rows = []
        self._placeholder = None
        self._drag_row = None
        self._drag_index = None
        self._press_gp = None
        self._dragging = False
        self.refresh()

    def host(self):
        """The widget rows are parented to."""
        return self._host

    def row_count(self):
        """The number of layer rows currently shown."""
        return len(self._rows)

    def drag_row(self):
        """The row being pressed or dragged, if any."""
        return self._drag_row

    def drag_index(self):
        """The insertion index under the cursor, or None."""
        return self._drag_index

    def slot_rect(self):
        """The thumbnail slot rectangle inside a row."""
        size = self.THUMB + 2 * self.SLOT_PAD
        return QtCore.QRect(self.EYE_W + 2, (self.ROW_H - size) // 2,
                            size, size)

    def name_x(self, row=None):
        """The left edge of the row name text."""
        return self.slot_rect().right() + 7

    def desired_height(self):
        """The height needed to show at most three rows."""
        shown = max(1, min(self.row_count(), self.MAX_ROWS))
        return shown * self.ROW_H + max(0, shown - 1) * self.ROW_GAP

    def refresh(self):
        """Rebuild the rows from the canvas layer stack."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []
        self._placeholder = None
        layers = list(reversed(self.canvas.layers()))
        if not layers:
            self._placeholder = QtWidgets.QLabel("No layers", self._host)
            self._placeholder.setObjectName("RefCanvasLayerEmpty")
            self._placeholder.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter)
            self._placeholder.setFixedHeight(self.ROW_H)
            self._layout.addWidget(self._placeholder)
        else:
            for index, layer in enumerate(layers):
                row = LayerRow(self, layer, index)
                self._layout.addWidget(row)
                self._rows.append(row)
        self._layout.addStretch(1)
        self.update_rows()

    def update_rows(self):
        """Repaint all rows after a selection or visibility change."""
        for row in self._rows:
            row.update()

    def begin_row_press(self, row, global_pos):
        """Start a possible row click or reorder drag."""
        self._drag_row = row
        self._drag_index = None
        self._press_gp = QtCore.QPoint(global_pos)
        self._dragging = False

    def move_row(self, global_pos):
        """Track a drag and publish the insertion line."""
        if self._drag_row is None or self._press_gp is None:
            return
        if not self._dragging:
            delta = global_pos - self._press_gp
            if abs(delta.x()) < 4 and abs(delta.y()) < 4:
                return
            self._dragging = True
        self._autoscroll(global_pos)
        self._drag_index = self._insertion_index(global_pos)
        for row in self._rows:
            row.update()

    def release_row(self, row, global_pos):
        """Select on a click, or reorder the stack after a drag."""
        if self._drag_row is not row:
            return
        dragging = self._dragging
        index = self._insertion_index(global_pos) if dragging else None
        current = self._rows.index(row) if row in self._rows else None
        self._drag_row = None
        self._drag_index = None
        self._press_gp = None
        self._dragging = False
        for other in self._rows:
            other.update()
        if current is None:
            return
        self.canvas.select_layer(row.layer)
        if index is None:
            return
        if index > current:
            index -= 1
        if index != current:
            self.canvas.move_layer_display(row.layer, index)

    def _insertion_index(self, global_pos):
        if not self._rows:
            return 0
        point = self._host.mapFromGlobal(global_pos)
        for index, row in enumerate(self._rows):
            geometry = row.geometry()
            if point.y() < geometry.top() + geometry.height() / 2.0:
                return index
        return len(self._rows)

    def _autoscroll(self, global_pos):
        bar = self.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        point = self.viewport().mapFromGlobal(global_pos)
        if point.y() < 8:
            bar.setValue(bar.value() - 8)
        elif point.y() > self.viewport().height() - 8:
            bar.setValue(bar.value() + 8)
