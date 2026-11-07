"""REFCANVAS dock panel: colour row, reference viewport and image row."""
from __future__ import annotations

import os
import uuid

try:
    from . import hotkeys, live, settings, store
    from .canvas import RefCanvas
    from .common import _log, _log_exc, _qt
    from .layers import LayerPanel
    from .swatches import SwatchGrid
    from .wheel import WheelPanel
except ImportError:
    import hotkeys
    import live
    import settings
    import store
    from canvas import RefCanvas
    from common import _log, _log_exc, _qt
    from layers import LayerPanel
    from swatches import SwatchGrid
    from wheel import WheelPanel

QtCore, QtGui, QtWidgets = _qt()

# Qt6 moved QShortcut from QtWidgets to QtGui; Qt5 only has the widget class.
QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut

# QKeySequence.ExactMatch lives in nested enums on Qt6.
_SEQ_MATCH = getattr(QtGui.QKeySequence, "SequenceMatch", QtGui.QKeySequence)
_EXACT_MATCH = _SEQ_MATCH.ExactMatch


def make_window_icon():
    """Draw the panel icon used by Painter to reopen the dock."""
    size = 32
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor(205, 205, 205), 1.5))
        painter.setBrush(QtGui.QColor(52, 62, 68))
        painter.drawRoundedRect(QtCore.QRectF(3.0, 5.0, 26.0, 22.0), 3.0, 3.0)
        painter.fillRect(QtCore.QRectF(7.0, 9.0, 7.0, 7.0),
                         QtGui.QColor(125, 198, 210))
        painter.fillRect(QtCore.QRectF(14.0, 16.0, 7.0, 7.0),
                         QtGui.QColor(125, 198, 210))
        painter.fillRect(QtCore.QRectF(14.0, 9.0, 7.0, 7.0),
                         QtGui.QColor(210, 210, 210))
        painter.fillRect(QtCore.QRectF(7.0, 16.0, 7.0, 7.0),
                         QtGui.QColor(210, 210, 210))
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


class SwatchPair(QtWidgets.QWidget):
    """Main and secondary colour swatches with a clickable swap arrow."""

    swap_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main = QtGui.QColor(91, 102, 166)
        self.secondary = QtGui.QColor(52, 57, 102)
        self._hover = False
        self.setFixedSize(36, 30)
        self.setMouseTracking(True)
        self.setToolTip("Main and secondary colours  /  "
                        "click the arrow or press Shift+X to swap")
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def set_main(self, color):
        """Set the main swatch colour."""
        self.main = QtGui.QColor(color)
        self.update()

    def set_secondary(self, color):
        """Set the secondary swatch colour."""
        self.secondary = QtGui.QColor(color)
        self.update()

    def swap(self):
        """Exchange the main and secondary colours."""
        self.main, self.secondary = self.secondary, self.main
        self.update()

    @staticmethod
    def _arrow_zone():
        return QtCore.QRectF(20.0, 0.0, 16.0, 14.0)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            self._paint_swatch(
                painter, QtCore.QRectF(12.0, 11.0, 22.0, 15.0),
                self.secondary, self.secondary.darker(140))
            self._paint_swatch(
                painter, QtCore.QRectF(2.0, 4.0, 22.0, 15.0),
                self.main, self.main.lighter(130))
            self._paint_swap(painter)
        finally:
            painter.end()

    @staticmethod
    def _paint_swatch(painter, rect, fill, edge):
        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, fill.lighter(110))
        gradient.setColorAt(1.0, fill.darker(108))
        painter.setPen(QtGui.QPen(edge, 1.0))
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawRoundedRect(rect, 2.0, 2.0)

    @staticmethod
    def _paint_swap(painter):
        pen = QtGui.QPen(QtGui.QColor(188, 188, 188), 1.2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        tip = QtCore.QPointF(25.0, 2.0)
        painter.drawLine(QtCore.QPointF(34.0, 10.0), tip)
        painter.drawLine(tip, QtCore.QPointF(27.8, 2.7))
        painter.drawLine(tip, QtCore.QPointF(26.0, 4.6))

    def mousePressEvent(self, event):
        if (event.button() == QtCore.Qt.MouseButton.LeftButton
                and self._arrow_zone().contains(event.position())):
            self.swap_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        hover = self._arrow_zone().contains(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor
                           if hover else QtCore.Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class LayerButton(QtWidgets.QPushButton):
    """LAYERS button that toggles a persistent layer list below it."""

    def __init__(self, parent=None):
        super().__init__("LAYERS", parent)
        self.setObjectName("RefCanvasLayers")
        self.setCheckable(True)
        self.setFixedSize(82, 24)
        self.setToolTip("Show layers; press again to hide")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor(198, 198, 198), 1.5)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            centre_x = self.width() - 11.0
            centre_y = self.height() / 2.0
            painter.drawLine(QtCore.QPointF(centre_x - 4.0, centre_y - 2.0),
                             QtCore.QPointF(centre_x, centre_y + 2.0))
            painter.drawLine(QtCore.QPointF(centre_x, centre_y + 2.0),
                             QtCore.QPointF(centre_x + 4.0, centre_y - 2.0))
        finally:
            painter.end()


class WheelButton(QtWidgets.QPushButton):
    """Wheel button with a leading chevron, matching the LAYERS style."""

    def __init__(self, parent=None):
        super().__init__("Wheel", parent)
        self.setObjectName("RefCanvasWheel")
        self.setCheckable(True)
        self.setToolTip("Show the wheel panel; press again to hide")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor(198, 198, 198), 1.5)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            centre_x = 9.0
            centre_y = self.height() / 2.0
            painter.drawLine(QtCore.QPointF(centre_x - 4.0, centre_y + 2.0),
                             QtCore.QPointF(centre_x, centre_y - 2.0))
            painter.drawLine(QtCore.QPointF(centre_x, centre_y - 2.0),
                             QtCore.QPointF(centre_x + 4.0, centre_y + 2.0))
        finally:
            painter.end()


class RefCanvasPanel(QtWidgets.QWidget):
    """The dockable REFCANVAS panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RefCanvasPanel")
        self.setWindowTitle("REFCANVAS")
        self.setWindowIcon(make_window_icon())
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(320, 360)
        self._last_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.PicturesLocation)
        self._live_color = None
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(60)
        self._live_timer.timeout.connect(self._flush_live)
        self._build_ui()
        self._apply_style()
        self._fit_buttons()
        self._setup_persistence()
        self._load_state()
        self.layer_panel.refresh()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 7)
        layout.setSpacing(6)

        self._top_row = QtWidgets.QWidget(self)
        self._top_row.setObjectName("RefCanvasTopRow")
        self._top_row.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        top_layout = QtWidgets.QHBoxLayout(self._top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)

        self.swatches = SwatchPair(self._top_row)
        self.swatches.swap_requested.connect(self._swap_colors)

        self.hex_edit = QtWidgets.QLineEdit("#5b66a6", self._top_row)
        self.hex_edit.setObjectName("RefCanvasHex")
        hex_width = max(72, self.hex_edit.fontMetrics().horizontalAdvance(
            "#5b66a6") + 26)
        self.hex_edit.setFixedSize(hex_width, 24)
        self.hex_edit.setToolTip("Main colour hex")
        self.hex_edit.returnPressed.connect(self._apply_hex)
        self.hex_edit.editingFinished.connect(self._apply_hex)

        self.btn_settings = QtWidgets.QPushButton("Settings", self._top_row)
        self.btn_settings.setObjectName("RefCanvasSmallButton")
        self.btn_settings.setToolTip("Open the settings window")
        self.btn_settings.clicked.connect(self._open_settings)

        self.btn_live = QtWidgets.QPushButton("LIVE ON", self._top_row)
        self.btn_live.setObjectName("RefCanvasLive")
        self.btn_live.setCheckable(True)
        self.btn_live.setFixedHeight(24)
        self.btn_live.setToolTip(
            "Apply picked colours to the paint tool Base Color (Alt+Z)."
            " Starts off every session; turns itself off on any internal"
            " memory fault.")
        self.btn_live.toggled.connect(self._on_live_toggled)

        self.btn_layers = LayerButton(self._top_row)
        self.btn_layers.clicked.connect(self._toggle_layers)

        top_layout.addWidget(self.swatches)
        top_layout.addWidget(self.hex_edit)
        top_layout.addWidget(self.btn_settings, 0,
                             QtCore.Qt.AlignmentFlag.AlignVCenter)
        top_layout.addStretch(1)
        top_layout.addWidget(self.btn_live, 0,
                             QtCore.Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(self.btn_layers, 0,
                             QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._top_row)

        self.canvas = RefCanvas(self)
        self.canvas.file_dropped.connect(self.load_image)
        self.canvas.layers_changed.connect(self._on_layers_changed)
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.color_picked.connect(self._on_color_picked)
        layout.addWidget(self.canvas, 1)

        self.swatch_grid = SwatchGrid(self)
        self.swatch_grid.color_selected.connect(self._on_color_picked)
        layout.addWidget(self.swatch_grid)

        self._transform_shortcut = QShortcut(
            hotkeys.key_sequence(hotkeys.combo("Transform Layer")), self)
        self._transform_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._transform_shortcut.activated.connect(self.canvas.begin_transform)

        self._fit_shortcut = QShortcut(
            QtGui.QKeySequence("Alt+F"), self)
        self._fit_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._fit_shortcut.activated.connect(self._fit_canvas)

        self._swatch_shortcut = QShortcut(
            hotkeys.key_sequence(hotkeys.combo("Add Swatch")), self)
        self._swatch_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._swatch_shortcut.activated.connect(self._add_swatch)

        self._live_shortcut = QShortcut(
            QtGui.QKeySequence("Alt+Z"), self)
        self._live_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._live_shortcut.activated.connect(self._toggle_live)

        self._delete_shortcut = QShortcut(
            QtGui.QKeySequence("Delete"), self)
        self._delete_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._delete_shortcut.activated.connect(self._delete_layer)

        self._apply_hotkeys()

        bottom = QtWidgets.QWidget(self)
        bottom.setObjectName("RefCanvasBottomRow")
        bottom.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        bottom.setFixedHeight(24)
        bottom_layout = QtWidgets.QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(6)
        top_align = QtCore.Qt.AlignmentFlag.AlignTop

        self.btn_wheel = WheelButton(bottom)
        self.btn_wheel.clicked.connect(self._toggle_wheel)

        self.btn_swatch_add = QtWidgets.QPushButton("+ Swatch", bottom)
        self.btn_swatch_add.setObjectName("RefCanvasSmallButton")
        self.btn_swatch_add.setToolTip(
            "Store the main colour in the next swatch (Alt+C)")
        self.btn_swatch_add.clicked.connect(self._add_swatch)

        self.btn_swatch_reset = QtWidgets.QPushButton("Reset", bottom)
        self.btn_swatch_reset.setObjectName("RefCanvasSmallButton")
        self.btn_swatch_reset.setToolTip("Clear every saved swatch")
        self.btn_swatch_reset.clicked.connect(self._reset_swatches)

        self.btn_reset_canvas = QtWidgets.QPushButton("Reset Canvas", bottom)
        self.btn_reset_canvas.setObjectName("RefCanvasButton")
        self.btn_reset_canvas.setToolTip(
            "Remove all layers and clear the canvas")
        self.btn_reset_canvas.clicked.connect(self.reset_canvas)

        self.btn_image = QtWidgets.QPushButton("Image", bottom)
        self.btn_image.setObjectName("RefCanvasButton")
        self.btn_image.setToolTip("Open an image as the base or a new layer")
        self.btn_image.clicked.connect(self.open_image_dialog)

        bottom_layout.addWidget(self.btn_wheel, 0, top_align)
        bottom_layout.addWidget(self.btn_swatch_add, 0, top_align)
        bottom_layout.addWidget(self.btn_swatch_reset, 0, top_align)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.btn_reset_canvas, 0, top_align)
        bottom_layout.addWidget(self.btn_image, 0, top_align)
        layout.addWidget(bottom)

        self._layers_popup = QtWidgets.QFrame(self)
        self._layers_popup.setObjectName("RefCanvasLayerPopup")
        self._layers_popup.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        popup_layout = QtWidgets.QVBoxLayout(self._layers_popup)
        popup_layout.setContentsMargins(4, 4, 4, 4)
        popup_layout.setSpacing(0)
        self.layer_panel = LayerPanel(self.canvas, self._layers_popup)
        popup_layout.addWidget(self.layer_panel)
        self._layers_popup.hide()

        self._wheel_popup = QtWidgets.QFrame(self)
        self._wheel_popup.setObjectName("RefCanvasWheelPopup")
        self._wheel_popup.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        wheel_layout = QtWidgets.QVBoxLayout(self._wheel_popup)
        wheel_layout.setContentsMargins(1, 1, 1, 1)
        wheel_layout.setSpacing(0)
        self.wheel_panel = WheelPanel(self._wheel_popup)
        self.wheel_panel.color_changed.connect(self._on_wheel_color)
        wheel_layout.addWidget(self.wheel_panel)
        self._wheel_popup.hide()

    def _apply_style(self):
        self.setStyleSheet(
            "QWidget#RefCanvasPanel, QWidget#RefCanvasTopRow,"
            " QWidget#RefCanvasBottomRow { background: #242424; }"
            "QLineEdit#RefCanvasHex {"
            " background: #2b2b2b; color: #b5b5b5;"
            " border: 1px solid #0d0d0d; border-radius: 3px;"
            " padding: 2px 6px; min-height: 18px; max-height: 18px;"
            " selection-background-color: #46537c; }"
            "QLineEdit#RefCanvasHex:focus { border-color: #4d6ba3; }"
            "QPushButton#RefCanvasButton {"
            " background: #2b2b2b; color: #d2d2d2; border: 1px solid #0d0d0d;"
            " border-radius: 3px; padding: 1px 9px; font-size: 9px;"
            " min-width: 0px; min-height: 16px; max-height: 16px; }"
            "QPushButton#RefCanvasButton:hover { background: #242424; }"
            "QPushButton#RefCanvasButton:pressed { background: #242424; }"
            "QPushButton#RefCanvasSmallButton {"
            " background: #2b2b2b; color: #d2d2d2; border: 1px solid #0d0d0d;"
            " border-radius: 3px; padding: 1px 7px; font-size: 9px;"
            " min-width: 0px; min-height: 16px; max-height: 16px; }"
            "QPushButton#RefCanvasSmallButton:hover { background: #242424; }"
            "QPushButton#RefCanvasSmallButton:pressed { background: #242424; }"
            "QPushButton#RefCanvasLive {"
            " background: #2b2b2b; color: #eeeeee; border: 1px solid #0d0d0d;"
            " border-radius: 3px; padding: 2px 7px; font-size: 9px;"
            " font-weight: bold; min-width: 0px;"
            " min-height: 18px; max-height: 18px; }"
            "QPushButton#RefCanvasLive:hover { background: #242424; }"
            "QPushButton#RefCanvasLive:checked {"
            " background: #2b2b2b; border: 1px solid #4f79bb; }"
            "QPushButton#RefCanvasLive:checked:hover { background: #242424; }"
            "QPushButton#RefCanvasLayers {"
            " background: #2b2b2b; color: #d4d4d4;"
            " border: 1px solid #0d0d0d; border-radius: 3px;"
            " padding: 2px 20px 2px 8px; text-align: left;"
            " font-size: 9px; min-width: 0px;"
            " min-height: 18px; max-height: 18px; }"
            "QPushButton#RefCanvasLayers:hover { background: #242424; }"
            "QPushButton#RefCanvasLayers:checked {"
            " background: #2b2b2b; border: 1px solid #4f79bb; }"
            "QPushButton#RefCanvasWheel {"
            " background: #2b2b2b; color: #d4d4d4;"
            " border: 1px solid #0d0d0d; border-radius: 3px;"
            " padding: 1px 8px 1px 20px; text-align: left;"
            " font-size: 9px; min-width: 0px;"
            " min-height: 16px; max-height: 16px; }"
            "QPushButton#RefCanvasWheel:hover { background: #242424; }"
            "QPushButton#RefCanvasWheel:checked {"
            " background: #2b2b2b; border: 1px solid #4f79bb; }"
            "QLineEdit#RefCanvasWheelField {"
            " background: #2b2b2b; color: #d2d2d2;"
            " border: 1px solid #0d0d0d; border-radius: 2px;"
            " padding: 0px 3px; font-size: 9px;"
            " selection-background-color: #46537c; }"
            "QLineEdit#RefCanvasWheelField:focus { border-color: #4d6ba3; }"
            "QLabel#RefCanvasWheelLabel { color: #b5b5b5; font-size: 9px; }"
            "QFrame#RefCanvasLayerPopup, QFrame#RefCanvasWheelPopup {"
            " background: #2b2b2b; border: 1px solid #454545;"
            " border-radius: 3px; }"
            "QScrollArea#RefCanvasLayerArea {"
            " background: transparent; border: none; }"
            "QWidget#RefCanvasLayerHost { background: transparent; }"
            "QLabel#RefCanvasLayerEmpty { color: #8d8d8d; font-size: 10px; }"
            "QScrollBar:vertical { background: transparent; width: 6px;"
            " margin: 0px; }"
            "QScrollBar::handle:vertical { background: #4a4a4a;"
            " border-radius: 3px; min-height: 14px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0px; }")

    # actions ------------------------------------------------------------
    def open_image_dialog(self):
        """Ask for an image file and load it."""
        path, _selected = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open reference image", self._last_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;"
            "All files (*)")
        if path:
            self.load_image(path)

    def load_image(self, path):
        """Load one image as the base or as a new collage layer."""
        path = os.path.normpath(str(path or ""))
        if not path:
            return False
        reader = QtGui.QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            reason = reader.errorString() or "unsupported image"
            _log("image load failed: %s: %s" % (path, reason))
            return False
        name = os.path.basename(path) or "Layer"
        had_canvas = self.canvas.has_image()
        layer = self.canvas.add_image(image, path, name)
        if layer is None:
            return False
        self._last_dir = os.path.dirname(path) or self._last_dir
        _log("layer added: %s (%dx%d)"
             % (path, image.width(), image.height()))
        if had_canvas:
            self.canvas.begin_transform()
        return True

    def reset_canvas(self):
        """Remove every layer and clear the saved document."""
        self.canvas.clear()
        try:
            self._doc_timer.stop()
        except Exception:
            pass
        self._save_document()
        _log("canvas reset")

    def _fit_canvas(self):
        """Fit and centre the layers in the viewport."""
        self.canvas.fit_to_view()

    def _fit_buttons(self):
        """Size the top and bottom buttons compactly to their labels."""
        small = QtGui.QFont(self.font())
        small.setPixelSize(9)
        regular = QtGui.QFont(small)
        regular.setPixelSize(9)
        specs = ((self.btn_live, small, 18, 24, True),
                 (self.btn_layers, small, 30, 24, False),
                 (self.btn_settings, small, 18, 20, False),
                 (self.btn_wheel, small, 40, 20, False),
                 (self.btn_swatch_add, small, 18, 20, False),
                 (self.btn_swatch_reset, small, 18, 20, False),
                 (self.btn_reset_canvas, regular, 20, 20, False),
                 (self.btn_image, regular, 20, 20, False))
        for button, font, pad, height, bold in specs:
            font = QtGui.QFont(font)
            font.setBold(bold)
            button.setFont(font)
            width = QtGui.QFontMetrics(font).horizontalAdvance(button.text())
            button.setFixedSize(max(34, width + pad), height)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                 QtWidgets.QSizePolicy.Policy.Fixed)

    def _add_swatch(self):
        """Store the main colour in the next swatch slot."""
        self.swatch_grid.add_color(self.swatches.main)

    def _reset_swatches(self):
        """Clear every saved swatch."""
        self.swatch_grid.clear_colors()

    def _delete_layer(self):
        """Delete the selected layer."""
        if self.canvas.delete_selected_layer():
            _log("layer deleted")

    # persistence --------------------------------------------------------
    def _setup_persistence(self):
        """Hook the swatch grid and canvas to the JSON state store."""
        self._layer_files = {}
        self._restoring = False
        self._ui_timer = QtCore.QTimer(self)
        self._ui_timer.setSingleShot(True)
        self._ui_timer.setInterval(350)
        self._ui_timer.timeout.connect(self._save_controls)
        self._doc_timer = QtCore.QTimer(self)
        self._doc_timer.setSingleShot(True)
        self._doc_timer.setInterval(600)
        self._doc_timer.timeout.connect(self._save_document)
        self.swatch_grid.changed.connect(self._save_swatches)
        self.canvas.layers_changed.connect(self._schedule_document_save)
        self.canvas.image_changed.connect(self._schedule_document_save)
        live.set_fault_callback(self._on_live_fault)

    def _load_state(self):
        """Load saved swatches and the last reference document."""
        state = store.load_state()
        corner = str(state.get("wheel_corner") or "bottom left")
        if corner not in ("bottom left", "bottom right", "top left",
                          "top right"):
            corner = "bottom left"
        self._wheel_corner = corner
        alt_pick = state.get("alt_pick")
        if not isinstance(alt_pick, bool):
            alt_pick = True
        self.canvas.set_alt_pick_required(alt_pick)
        colors = state.get("swatches")
        if isinstance(colors, list):
            self.swatch_grid.set_colors(colors, state.get("swatch_next", 0))
        top = state.get("colors")
        if isinstance(top, dict):
            main = QtGui.QColor(str(top.get("main") or ""))
            if main.isValid():
                self.swatches.set_main(main)
                self.hex_edit.setText(main.name())
            secondary = QtGui.QColor(str(top.get("secondary") or ""))
            if secondary.isValid():
                self.swatches.set_secondary(secondary)
        self.wheel_panel.set_color(self.swatches.main)
        # Live On intentionally starts off every session; the raw colour
        # bridge is only safe to run when the user opts in freshly.
        if state.get("wheel_open"):
            self.btn_wheel.setChecked(True)
            QtCore.QTimer.singleShot(0, self._restore_wheel_open)
        doc = state.get("document")
        if not isinstance(doc, dict):
            return
        try:
            width = int(doc.get("width") or 0)
            height = int(doc.get("height") or 0)
        except Exception:
            width = 0
            height = 0
        entries = []
        files = []
        for item in doc.get("layers") or []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("file") or "")
            if not filename:
                continue
            image = QtGui.QImage(os.path.join(store.LAYER_DIR, filename))
            if image.isNull():
                _log("saved layer missing: %s" % filename)
                continue
            try:
                x = float(item.get("x") or 0.0)
                y = float(item.get("y") or 0.0)
            except Exception:
                x = 0.0
                y = 0.0
            entries.append({
                "image": image,
                "name": str(item.get("name") or "Layer"),
                "path": str(item.get("path") or ""),
                "x": x,
                "y": y,
                "visible": bool(item.get("visible", True)),
            })
            files.append(filename)
        if not entries:
            return
        self._restoring = True
        try:
            self.canvas.restore_document(
                QtCore.QSize(width, height), entries, doc.get("selected"))
        finally:
            self._restoring = False
        for layer, filename in zip(self.canvas.layers(), files):
            self._layer_files[id(layer)] = {
                "name": filename,
                "key": layer.image.cacheKey(),
            }
        self.layer_panel.refresh()

    def _schedule_document_save(self):
        """Debounce a save after the canvas contents change."""
        if getattr(self, "_restoring", False):
            return
        self._doc_timer.stop()
        self._doc_timer.start()

    def _schedule_ui_save(self):
        """Debounce a save of the top-row controls."""
        self._ui_timer.stop()
        self._ui_timer.start()

    def _save_controls(self):
        """Persist the top-row colours, Live On and the wheel panel flag."""
        store.save_controls(self.swatches.main.name(),
                            self.swatches.secondary.name(),
                            self.btn_live.isChecked(),
                            self.btn_wheel.isChecked())

    def _save_swatches(self):
        """Persist the saved swatch colours."""
        colors = [color.name() if color is not None else None
                  for color in self.swatch_grid.colors()]
        store.save_swatches(colors, self.swatch_grid.next_index())

    def _save_document(self):
        """Persist the layer document and its pixel files."""
        if not hasattr(self, "_layer_files"):
            return
        layers = self.canvas.layers()
        if not layers:
            self._layer_files = {}
            store.clear_document()
            return
        try:
            os.makedirs(store.LAYER_DIR, exist_ok=True)
        except Exception:
            _log("layer folder create failed")
            return
        used = set()
        cache = {}
        specs = []
        for layer in layers:
            ref = self._layer_files.get(id(layer)) or {}
            filename = ref.get("name") or (
                "layer_%s.png" % uuid.uuid4().hex[:12])
            target = os.path.join(store.LAYER_DIR, filename)
            key = layer.image.cacheKey()
            if ref.get("key") != key or not os.path.isfile(target):
                if (layer.image.isNull()
                        or not layer.image.save(target, "PNG")):
                    _log("layer image save failed: %s" % layer.name)
                    continue
                ref = {"name": filename, "key": key}
            used.add(filename)
            cache[id(layer)] = ref
            specs.append({
                "file": filename,
                "name": layer.name,
                "path": layer.path,
                "x": layer.x,
                "y": layer.y,
                "visible": bool(layer.visible),
            })
        self._layer_files = cache
        if not specs:
            store.clear_document()
            return
        selected = None
        current = self.canvas.selected_layer()
        if current in layers:
            selected = layers.index(current)
        size = self.canvas.document_size()
        store.save_document({
            "width": size.width(),
            "height": size.height(),
            "selected": selected,
            "layers": specs,
        })
        store.prune_layer_files(used)

    def flush_state(self):
        """Persist swatches and the document before teardown."""
        try:
            self._doc_timer.stop()
        except Exception:
            pass
        try:
            self._ui_timer.stop()
        except Exception:
            pass
        try:
            self._live_timer.stop()
        except Exception:
            pass
        self._save_controls()
        self._save_swatches()
        self._save_document()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def _swap_colors(self):
        """Exchange the main and secondary colours."""
        self.swatches.swap()
        self.hex_edit.setText(self.swatches.main.name())
        self.wheel_panel.set_color(self.swatches.main)
        self._schedule_ui_save()
        live.refresh()
        self._apply_live(self.swatches.main)

    def _apply_hex(self):
        """Apply the typed hex colour to the main swatch."""
        text = self.hex_edit.text().strip()
        if not text:
            self.hex_edit.setText(self.swatches.main.name())
            return
        if not text.startswith("#"):
            text = "#" + text
        color = QtGui.QColor(text)
        if not color.isValid():
            self.hex_edit.setText(self.swatches.main.name())
            return
        self.swatches.set_main(color)
        self.hex_edit.setText(self.swatches.main.name())
        self.wheel_panel.set_color(color)
        self._schedule_ui_save()

    def _on_color_picked(self, color):
        """Show a picked colour in the main swatch and hex field."""
        self.swatches.set_main(color)
        self.hex_edit.setText(self.swatches.main.name())
        self.wheel_panel.set_color(color)
        self._schedule_ui_save()
        self._apply_live(color)

    def _on_wheel_color(self, color):
        """Show a colour picked on the wheel without resetting its knobs."""
        self.swatches.set_main(color)
        self.hex_edit.setText(self.swatches.main.name())
        self._schedule_ui_save()
        self._apply_live(color)

    def _toggle_live(self):
        """Flip the Live On state from the Alt+Z shortcut."""
        self.btn_live.setChecked(not self.btn_live.isChecked())

    @staticmethod
    def _typing_focus():
        """True when the focused widget accepts typed text."""
        focus = QtWidgets.QApplication.focusWidget()
        if focus is None:
            return False
        try:
            return isinstance(focus, (
                QtWidgets.QLineEdit, QtWidgets.QTextEdit,
                QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox))
        except Exception:
            return False

    def _apply_hotkeys(self):
        """Push the configured combos into shortcuts and the swap filter."""
        enabled = hotkeys.hotkeys_enabled()
        self._swap_sequence = (
            hotkeys.key_sequence(hotkeys.combo("Color Swap"))
            if enabled else QtGui.QKeySequence())
        for name, shortcut in (("Transform Layer", self._transform_shortcut),
                               ("Add Swatch", self._swatch_shortcut)):
            if shortcut is None:
                continue
            try:
                shortcut.setEnabled(enabled)
                if enabled:
                    shortcut.setKey(
                        hotkeys.key_sequence(hotkeys.combo(name)))
            except Exception:
                _log_exc("hotkey apply %s" % name)

    def _on_hotkey_changed(self, _name, _combo):
        """Re-wire the shortcuts after the settings dialog captured a combo."""
        self._apply_hotkeys()

    def _on_hotkeys_enabled(self, _on):
        """Apply the master hotkey switch from the settings dialog."""
        self._apply_hotkeys()

    def eventFilter(self, obj, event):
        """Swap the top-row colours with the configured hotkey in Painter."""
        try:
            if (event.type() == QtCore.QEvent.Type.KeyPress
                    and not event.isAutoRepeat()
                    and not self._typing_focus()
                    and QtWidgets.QApplication.activeModalWidget() is None
                    and QtWidgets.QApplication.activePopupWidget() is None):
                pressed = QtGui.QKeySequence(
                    int(event.modifiers()) | int(event.key()))
                swap = getattr(self, "_swap_sequence", None)
                if (swap is not None and not swap.isEmpty()
                        and swap.matches(pressed) == _EXACT_MATCH):
                    self._swap_colors()
                    return True
        except Exception:
            _log_exc("swap shortcut")
        return super().eventFilter(obj, event)

    def _apply_live(self, color):
        """Queue the picked colour for the paint tool while Live On is set."""
        if not self.btn_live.isChecked():
            return
        self._live_color = QtGui.QColor(color)
        self._live_timer.start()

    def _flush_live(self):
        """Send the last picked colour to Painter."""
        color = self._live_color
        if color is None or not self.btn_live.isChecked():
            return
        try:
            live.apply_color(color)
        except Exception:
            _log_exc("live colour apply")

    def _on_live_toggled(self, checked):
        """Drop the cached target when Live On changes and stop pending work."""
        if checked:
            live.refresh()
        else:
            self._live_timer.stop()
        self._schedule_ui_save()

    def _on_live_fault(self):
        """A raw colour write hit bad memory; switch Live Off immediately."""
        try:
            _log("live: memory fault detected; Live On disabled")
        except Exception:
            pass
        self.btn_live.setChecked(False)
        live.refresh()

    # layers -------------------------------------------------------------
    def _toggle_layers(self):
        if self._layers_popup.isVisible():
            self._layers_popup.hide()
            self.btn_layers.setChecked(False)
            return
        self.layer_panel.refresh()
        self._place_layers()
        self._layers_popup.show()
        self._layers_popup.raise_()
        self.btn_layers.setChecked(True)

    def _place_layers(self):
        width = max(120, min(160, self.width() - 12))
        self._layers_popup.setFixedWidth(width)
        self._layers_popup.setFixedHeight(
            self.layer_panel.desired_height() + 8)
        # The wheel owns the canvas top-right corner when snapped there, so
        # the layer list drops to the canvas bottom-right instead.
        if getattr(self, "_wheel_corner", "bottom left") == "top right":
            rect = self.canvas.geometry()
            x = max(2, rect.right() - width - 2)
            y = max(2, rect.bottom() - self._layers_popup.height() - 1)
            self._layers_popup.move(x, y)
            return
        top = self._top_row.geometry().bottom() + 2
        self._layers_popup.move(self.width() - width - 6, top)

    def _on_layers_changed(self):
        self.layer_panel.refresh()
        if self._layers_popup.isVisible():
            self._place_layers()
            self._layers_popup.raise_()

    def _on_selection_changed(self):
        self.layer_panel.update_rows()

    # wheel --------------------------------------------------------------
    def _toggle_wheel(self):
        """Show or hide the wheel panel."""
        visible = not self._wheel_popup.isVisible()
        if visible:
            self._place_wheel()
            self._wheel_popup.show()
            self._wheel_popup.raise_()
        else:
            self._wheel_popup.hide()
        self.btn_wheel.setChecked(visible)
        self._schedule_ui_save()

    def _place_wheel(self):
        """Put the wheel panel in the configured canvas corner."""
        width = max(96, min(128, self.width() - 10))
        height = int(round(width * 1.3))
        rect = self.canvas.geometry()
        self._wheel_popup.setFixedSize(width, height)
        corner = getattr(self, "_wheel_corner", "bottom left")
        if corner == "bottom right":
            x = max(2, rect.right() - width - 2)
            y = max(2, rect.bottom() - height - 1)
        elif corner == "top left":
            x = max(2, rect.left() + 2)
            y = max(2, rect.top() + 2)
        elif corner == "top right":
            x = max(2, rect.right() - width - 2)
            y = max(2, rect.top() + 2)
        else:  # "bottom left" (default)
            x = max(2, rect.left() + 2)
            y = max(2, rect.bottom() - height - 1)
        self._wheel_popup.move(x, y)

    def _open_settings(self):
        """Open the settings dialog with the current values."""
        settings.show_settings(
            parent=self,
            wheel_corner=getattr(self, "_wheel_corner", "bottom left"),
            alt_pick=self.canvas.alt_pick_required,
            on_wheel_corner=self._on_wheel_corner_changed,
            on_alt_pick=self._on_alt_pick_changed,
            on_hotkey_changed=self._on_hotkey_changed,
            on_hotkeys_enabled=self._on_hotkeys_enabled)

    def _on_wheel_corner_changed(self, corner):
        """Persist the new wheel corner and re-place an open wheel."""
        corner = str(corner)
        if corner not in ("bottom left", "bottom right", "top left",
                          "top right"):
            return
        self._wheel_corner = corner
        store.save_wheel_corner(corner)
        if self._wheel_popup.isVisible():
            self._place_wheel()
            self._wheel_popup.raise_()

    def _on_alt_pick_changed(self, required):
        """Persist the Alt-for-pick switch and update the canvas."""
        self.canvas.set_alt_pick_required(required)
        store.save_alt_pick(required)

    def _restore_wheel_open(self):
        """Open the wheel panel after a restart when it was left open."""
        if not self.btn_wheel.isChecked():
            return
        self._place_wheel()
        self._wheel_popup.show()
        self._wheel_popup.raise_()

    def showEvent(self, event):
        """Place the wheel panel once the dock becomes visible."""
        super().showEvent(event)
        wheel = getattr(self, "_wheel_popup", None)
        button = getattr(self, "btn_wheel", None)
        if wheel is not None and button is not None and button.isChecked():
            self._place_wheel()
            wheel.show()
            wheel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        popup = getattr(self, "_layers_popup", None)
        if popup is not None and popup.isVisible():
            self._place_layers()
            popup.raise_()
        wheel = getattr(self, "_wheel_popup", None)
        if wheel is not None and wheel.isVisible():
            self._place_wheel()
            wheel.raise_()
