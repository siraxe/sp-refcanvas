"""Reference canvas viewport: image display, fit, pan and zoom."""
from __future__ import annotations

try:
    from .common import _log_exc, _qt
    from .layer_transform import LayerTransform
    from .layers import RefLayer
    from .pickcursor import pick_cursor
except ImportError:
    from common import _log_exc, _qt
    from layer_transform import LayerTransform
    from layers import RefLayer
    from pickcursor import pick_cursor

QtCore, QtGui, QtWidgets = _qt()


class RefCanvas(QtWidgets.QWidget):
    """A reference-image viewport with fit, pan and cursor-anchored zoom."""

    image_changed = QtCore.Signal()
    layers_changed = QtCore.Signal()
    selection_changed = QtCore.Signal()
    zoom_changed = QtCore.Signal(float)
    file_dropped = QtCore.Signal(str)
    color_picked = QtCore.Signal(QtGui.QColor)

    ZOOM_MIN = 0.02
    ZOOM_MAX = 16.0
    ZOOM_DRAG = 1.005
    FIT_MARGIN = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RefCanvasCanvas")
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(160, 120)
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self._layers = []
        self._doc_size = QtCore.QSize(0, 0)
        self._zoom = 1.0
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._fit_mode = True
        self._space = False
        self._panning = False
        self._pan_last = None
        self._pan_button = None
        self._dolly = False
        self._dolly_last = None
        self._dolly_anchor = None
        self._dolly_screen = None
        self._selected = None
        self._transform = LayerTransform(self)
        self._picking = False
        self._alt_held = False
        self._pick_cursor = None
        self.alt_pick_required = True
        self._checker = None
    # image / view state -------------------------------------------------
    def image(self):
        """Return the base layer image, or a null image."""
        return self._layers[0].image if self._layers else QtGui.QImage()

    def image_path(self):
        """Return the source path of the base layer, if known."""
        return self._layers[0].path if self._layers else ""

    def layers(self):
        """Return the layers from bottom to top."""
        return list(self._layers)

    def document_size(self):
        """Return the collage size set by the first image."""
        return QtCore.QSize(self._doc_size)

    def has_image(self):
        """True when the document holds at least one layer."""
        return bool(self._layers) and not self._doc_size.isEmpty()

    def selected_layer(self):
        """Return the selected layer if it is still in the stack."""
        return self._selected if self._selected in self._layers else None

    def select_layer(self, layer):
        """Select a layer, or clear the selection with None."""
        if layer not in self._layers:
            layer = None
        if (self._transform.active
                and layer is not self._transform.layer):
            self._transform.cancel()
        if layer is self._selected:
            return
        self._selected = layer
        self.selection_changed.emit()
        self.update()

    def set_layer_visible(self, layer, visible):
        """Show or hide one layer in the stack."""
        if layer not in self._layers:
            return
        visible = bool(visible)
        if layer.visible == visible:
            return
        layer.visible = visible
        if (not visible and self._transform.active
                and self._transform.layer is layer):
            self._transform.cancel()
        self.layers_changed.emit()
        self.image_changed.emit()
        self.update()

    def move_layer_display(self, layer, display_index):
        """Move a layer to an index counted from the top of the list."""
        if layer not in self._layers:
            return
        display = list(reversed(self._layers))
        display.remove(layer)
        index = max(0, min(int(display_index), len(display)))
        display.insert(index, layer)
        self._layers = list(reversed(display))
        self.layers_changed.emit()
        self.update()

    def delete_selected_layer(self):
        """Delete the selected layer and select a neighbour."""
        layer = self.selected_layer()
        if layer is None:
            return False
        if self._transform.active:
            self._transform.cancel()
        index = self._layers.index(layer)
        self._layers.pop(index)
        if not self._layers:
            self.clear()
            return True
        self._selected = self._layers[min(index, len(self._layers) - 1)]
        self.layers_changed.emit()
        self.selection_changed.emit()
        self.image_changed.emit()
        self.update()
        return True

    def restore_document(self, doc_size, entries, selected_index=None):
        """Restore layers and the document size from saved state."""
        if self._transform.active:
            self._transform.cancel()
        self._layers = []
        self._selected = None
        size = QtCore.QSize(doc_size)
        width = size.width()
        height = size.height()
        for entry in entries or []:
            image = entry.get("image")
            if image is None or image.isNull():
                continue
            x = float(entry.get("x") or 0.0)
            y = float(entry.get("y") or 0.0)
            layer = RefLayer(image, entry.get("name") or "Layer",
                             entry.get("path") or "", x, y)
            layer.visible = bool(entry.get("visible", True))
            self._layers.append(layer)
            width = max(width, int(x) + image.width())
            height = max(height, int(y) + image.height())
        self._doc_size = QtCore.QSize(max(0, width), max(0, height))
        if self._layers:
            try:
                index = int(selected_index)
            except Exception:
                index = -1
            if not (0 <= index < len(self._layers)):
                index = len(self._layers) - 1
            self._selected = self._layers[index]
        self._fit_mode = True
        if self.has_image() and self.width() > 0 and self.height() > 0:
            self.fit_to_view()
        self.layers_changed.emit()
        self.selection_changed.emit()
        self.image_changed.emit()
        self.update()

    def layer_at(self, x, y):
        """Return the topmost visible layer whose pixels cover a point."""
        if not self.has_image():
            return None
        for layer in reversed(self._layers):
            if not layer.visible or layer.image.isNull():
                continue
            local = self._layer_local_point(layer, x, y)
            if local is None:
                continue
            local_x = int(local[0])
            local_y = int(local[1])
            if (0 <= local_x < layer.image.width()
                    and 0 <= local_y < layer.image.height()
                    and layer.image.pixelColor(local_x, local_y).alpha() > 0):
                return layer
        return None

    def _layer_local_point(self, layer, x, y):
        return x - layer.x, y - layer.y

    def _add_base(self, image, path, name):
        self._layers.append(RefLayer(image, name, path, 0, 0))
        self._selected = self._layers[-1]
        self._doc_size = image.size()
        self._fit_mode = True
        if self.width() > 0 and self.height() > 0:
            self.fit_to_view()
        else:
            self._zoom = 1.0
            self._pan = QtCore.QPointF(0.0, 0.0)
            self.zoom_changed.emit(self._zoom)
        self.layers_changed.emit()
        self.selection_changed.emit()
        self.image_changed.emit()
        self.update()

    def add_image(self, image, path="", name=""):
        """Add an image as the base layer or a centred collage layer."""
        image = QtGui.QImage(image) if image is not None else QtGui.QImage()
        if image.isNull():
            return None
        if self._transform.active:
            self._transform.cancel()
        if not self._layers:
            self._add_base(image, path, name)
            return self._layers[-1]
        layer = RefLayer(
            image, name, path,
            (self._doc_size.width() - image.width()) / 2.0,
            (self._doc_size.height() - image.height()) / 2.0)
        self._layers.append(layer)
        self._selected = layer
        self.layers_changed.emit()
        self.selection_changed.emit()
        self.image_changed.emit()
        self.update()
        return layer

    def set_image(self, image, path="", name=""):
        """Replace the document with one base image and fit it."""
        if self._transform.active:
            self._transform.cancel()
        self._selected = None
        self._layers = []
        self._doc_size = QtCore.QSize(0, 0)
        image = QtGui.QImage(image) if image is not None else QtGui.QImage()
        if image.isNull():
            self.clear()
            return
        self._add_base(image, path, name)

    def clear(self):
        """Unload every layer and show the drop hint."""
        if self._transform.active:
            self._transform.cancel()
        self._selected = None
        self._layers = []
        self._doc_size = QtCore.QSize(0, 0)
        self._zoom = 1.0
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._fit_mode = True
        self.zoom_changed.emit(self._zoom)
        self.layers_changed.emit()
        self.selection_changed.emit()
        self.image_changed.emit()
        self.update()

    def zoom(self):
        """Current view scale (1.0 means 100%)."""
        return self._zoom

    def fit_to_view(self):
        """Fit the whole image into the viewport."""
        if not self.has_image() or self.width() <= 0 or self.height() <= 0:
            return
        available_w = max(1, self.width() - 2 * self.FIT_MARGIN)
        available_h = max(1, self.height() - 2 * self.FIT_MARGIN)
        zoom = min(available_w / float(self._doc_size.width()),
                   available_h / float(self._doc_size.height()))
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self._zoom = zoom
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._fit_mode = True
        self._update_cursor()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def actual_size(self):
        """Show the image at 100% and centre it."""
        if not self.has_image():
            return
        self._zoom = 1.0
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._fit_mode = False
        self._update_cursor()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def image_rect(self):
        """The image rectangle in widget coordinates."""
        if not self.has_image():
            return QtCore.QRectF()
        width = self._doc_size.width() * self._zoom
        height = self._doc_size.height() * self._zoom
        center = QtCore.QPointF(self.width() / 2.0 + self._pan.x(),
                                self.height() / 2.0 + self._pan.y())
        return QtCore.QRectF(center.x() - width / 2.0,
                             center.y() - height / 2.0, width, height)

    def image_from_view(self, point):
        """Map a widget point to image pixels."""
        rect = self.image_rect()
        if rect.isEmpty() or self._zoom <= 0.0:
            return QtCore.QPointF()
        return QtCore.QPointF(
            (point.x() - rect.left()) / self._zoom,
            (point.y() - rect.top()) / self._zoom)

    def view_from_image(self, point):
        """Map an image-pixel point to widget coordinates."""
        rect = self.image_rect()
        return QtCore.QPointF(
            rect.left() + point.x() * self._zoom,
            rect.top() + point.y() * self._zoom)

    def color_at_view(self, point):
        """Return the image colour under a widget point, or None."""
        image_point = self.image_from_view(point)
        return self.color_at_image(image_point.x(), image_point.y())

    def color_at_image(self, x, y):
        """Return the topmost opaque layer colour at a document pixel."""
        if not self.has_image():
            return None
        if (x < 0 or y < 0 or x >= self._doc_size.width()
                or y >= self._doc_size.height()):
            return None
        for layer in reversed(self._layers):
            if not layer.visible:
                continue
            local = self._layer_local_point(layer, x, y)
            if local is None:
                continue
            local_x = int(local[0])
            local_y = int(local[1])
            if (0 <= local_x < layer.image.width()
                    and 0 <= local_y < layer.image.height()):
                color = layer.image.pixelColor(local_x, local_y)
                if color.alpha() > 0:
                    return color
        return None

    # transform ----------------------------------------------------------
    def transform_active(self):
        """True while a Ctrl+T transform session is open."""
        return self._transform.active

    def begin_transform(self):
        """Open a free-transform session for the selected layer."""
        if self._transform.active:
            return True
        return self._transform.begin()

    def finish_transform(self, commit=True):
        """Close the transform session, optionally baking its result."""
        return self._transform.finish(commit)

    def _top_visible_layer(self):
        for layer in reversed(self._layers):
            if layer.visible and not layer.image.isNull():
                return layer
        return None

    # colour picking -----------------------------------------------------
    def set_alt_pick_required(self, required):
        """Require Alt for picking (True) or allow plain left-drag picking."""
        self.alt_pick_required = bool(required)
        self._update_cursor()

    def _picker(self):
        """Return the shared eyedropper cursor."""
        if self._pick_cursor is None:
            self._pick_cursor = pick_cursor()
        return self._pick_cursor

    def _pick_at(self, point):
        """Sample the topmost opaque layer colour under a view point."""
        color = self.color_at_view(point)
        if color is None or color.alpha() <= 0:
            return None
        picked = QtGui.QColor(color.red(), color.green(), color.blue())
        self.color_picked.emit(picked)
        return picked

    # input --------------------------------------------------------------
    def wheelEvent(self, event):
        if not self.has_image():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.15 ** (delta / 120.0)
        self._zoom_at(event.position(), self._zoom * factor)
        event.accept()

    def _zoom_at(self, view_point, wanted):
        if not self.has_image():
            return
        image_point = self.image_from_view(view_point)
        self._set_zoom_anchored(wanted, image_point, view_point)

    def _set_zoom_anchored(self, wanted, image_point, view_point):
        target = max(self.ZOOM_MIN, min(self.ZOOM_MAX, wanted))
        if abs(target - self._zoom) < 1e-9:
            return
        self._zoom = target
        width = self._doc_size.width() * self._zoom
        height = self._doc_size.height() * self._zoom
        self._pan = QtCore.QPointF(
            view_point.x() - self.width() / 2.0 + width / 2.0
            - image_point.x() * self._zoom,
            view_point.y() - self.height() / 2.0 + height / 2.0
            - image_point.y() * self._zoom)
        self._fit_mode = False
        self._update_cursor()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def mousePressEvent(self, event):
        if self._dolly and event.button() != QtCore.Qt.MouseButton.RightButton:
            event.accept()
            return
        mods = event.modifiers()
        alt = bool(mods & QtCore.Qt.KeyboardModifier.AltModifier)
        if alt != self._alt_held:
            self._alt_held = alt
            self._update_cursor()
        if (self.has_image()
                and event.button() == QtCore.Qt.MouseButton.RightButton
                and alt and not self._transform.active):
            self._end_pan()
            self._dolly = True
            self._dolly_last = event.position()
            self._dolly_anchor = self.image_from_view(event.position())
            self._dolly_screen = event.position()
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
            event.accept()
            return
        pan_button = event.button() == QtCore.Qt.MouseButton.MiddleButton
        space_left = (event.button() == QtCore.Qt.MouseButton.LeftButton
                      and self._space)
        if self.has_image() and (pan_button or space_left):
            self._end_dolly()
            self._panning = True
            self._pan_last = event.position()
            self._pan_button = event.button()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._transform.active:
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            self._transform.press(event)
            event.accept()
            return
        left = event.button() == QtCore.Qt.MouseButton.LeftButton
        if left and not self._space:
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            if self.has_image() and (alt or not self.alt_pick_required):
                self._picking = True
                self._pick_at(event.position())
                event.accept()
                return
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        held = event.buttons()
        alt = bool(event.modifiers()
                   & QtCore.Qt.KeyboardModifier.AltModifier)
        changed = alt != self._alt_held
        self._alt_held = alt
        if self._dolly:
            if held & QtCore.Qt.MouseButton.RightButton:
                position = event.position()
                delta = position - self._dolly_last
                self._dolly_last = position
                step = delta.x() + delta.y()
                if step:
                    self._set_zoom_anchored(
                        self._zoom * (self.ZOOM_DRAG ** step),
                        self._dolly_anchor, self._dolly_screen)
                event.accept()
                return
            self._end_dolly()
        if self._panning:
            if self._pan_button is None or held & self._pan_button:
                if self._pan_last is not None:
                    self._pan += event.position() - self._pan_last
                    self._pan_last = event.position()
                    self.update()
                event.accept()
                return
            self._end_pan()
        if self._transform.active:
            self._transform.move(event)
            event.accept()
            return
        if self._picking:
            if held & QtCore.Qt.MouseButton.LeftButton:
                self._pick_at(event.position())
                event.accept()
                return
            self._picking = False
            self._update_cursor()
        if changed:
            self._update_cursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dolly and event.button() == QtCore.Qt.MouseButton.RightButton:
            self._end_dolly()
            event.accept()
            return
        if self._panning and event.button() == self._pan_button:
            self._end_pan()
            event.accept()
            return
        if self._dolly or self._panning:
            event.accept()
            return
        if self._transform.active:
            self._transform.release(event)
            event.accept()
            return
        if (self._picking
                and event.button() == QtCore.Qt.MouseButton.LeftButton):
            self._picking = False
            self._update_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _end_pan(self):
        self._panning = False
        self._pan_last = None
        self._pan_button = None
        self._update_cursor()

    def _end_dolly(self):
        self._dolly = False
        self._dolly_last = None
        self._dolly_anchor = None
        self._dolly_screen = None
        self._update_cursor()

    def mouseDoubleClickEvent(self, event):
        if (event.button() == QtCore.Qt.MouseButton.LeftButton
                and self.has_image()):
            if self._transform.active:
                self._transform.finish(True)
            else:
                self.fit_to_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if (event.key() == QtCore.Qt.Key.Key_Space
                and not event.isAutoRepeat()):
            self._space = True
            self._update_cursor()
            event.accept()
            return
        if (event.key() == QtCore.Qt.Key.Key_Alt
                and not event.isAutoRepeat()):
            self._alt_held = True
            self._update_cursor()
            event.accept()
            return
        if self._transform.active and self._transform.key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if (event.key() == QtCore.Qt.Key.Key_Space
                and not event.isAutoRepeat()):
            self._space = False
            if not self._panning:
                self._update_cursor()
            event.accept()
            return
        if (event.key() == QtCore.Qt.Key.Key_Alt
                and not event.isAutoRepeat()):
            self._alt_held = False
            if not self._picking:
                self._update_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _update_cursor(self):
        if self._dolly:
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        elif self._panning:
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        elif self._space and self.has_image():
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        elif self._transform.active:
            self._transform.refresh_cursor()
        elif (self.alt_pick_required
                and (self._picking or (self._alt_held and self.has_image()))):
            self.setCursor(self._picker())
        else:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        handled = False
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                handled = True
        if handled:
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    # painting -----------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self.has_image():
            self.fit_to_view()

    def _checker_brush(self):
        if self._checker is None:
            pixmap = QtGui.QPixmap(16, 16)
            pixmap.fill(QtGui.QColor(70, 70, 70))
            painter = QtGui.QPainter(pixmap)
            try:
                painter.fillRect(0, 0, 8, 8, QtGui.QColor(54, 54, 54))
                painter.fillRect(8, 8, 8, 8, QtGui.QColor(54, 54, 54))
            finally:
                painter.end()
            self._checker = QtGui.QBrush(pixmap)
        return self._checker

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            painter.fillRect(self.rect(), QtGui.QColor(33, 33, 33))
            if not self.has_image():
                self._paint_empty(painter)
                return
            rect = self.image_rect()
            painter.save()
            try:
                painter.setClipRect(self.rect())
                painter.translate(rect.topLeft())
                painter.fillRect(QtCore.QRectF(0.0, 0.0, rect.width(),
                                               rect.height()),
                                 self._checker_brush())
            finally:
                painter.restore()
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.save()
            try:
                painter.setClipRect(rect)
                for layer in self._layers:
                    if not layer.visible:
                        continue
                    if (self._transform.active
                            and self._transform.layer is layer):
                        self._transform.paint_preview(painter, rect)
                        continue
                    target = QtCore.QRectF(
                        rect.left() + layer.x * self._zoom,
                        rect.top() + layer.y * self._zoom,
                        layer.image.width() * self._zoom,
                        layer.image.height() * self._zoom)
                    painter.drawImage(target, layer.image,
                                      QtCore.QRectF(layer.image.rect()))
            finally:
                painter.restore()
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90), 1.0))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-0.5, -0.5, -0.5, -0.5))
            if self._transform.active:
                self._transform.paint_overlay(painter)
        except Exception:
            _log_exc("canvas paint")
        finally:
            painter.end()

    def _paint_empty(self, painter):
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QtGui.QPen(QtGui.QColor(48, 48, 48), 1.0,
                                  QtCore.Qt.PenStyle.DashLine))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(150, 150, 150))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter,
                         "Drop a reference image\nor use Image")
