"""Modal free-transform session for one REFCANVAS layer."""
from __future__ import annotations

import math

try:
    from .common import _log_exc, _qt
    from .transform_overlay import draw_overlay
    from .transform_geom import (HIT_PX, WARP_CELLS, WarpMesh, affine_tri,
                                 cell_flat, constrain, h_apply, h_inv,
                                 keep_convex, quad_inside, qtransform,
                                 rect_to_quad)
except ImportError:
    from common import _log_exc, _qt
    from transform_overlay import draw_overlay
    from transform_geom import (HIT_PX, WARP_CELLS, WarpMesh, affine_tri,
                                cell_flat, constrain, h_apply, h_inv,
                                keep_convex, quad_inside, qtransform,
                                rect_to_quad)

QtCore, QtGui, QtWidgets = _qt()


class LayerTransform:
    """The modal Ctrl+T box, warp mesh and right-click menu for one layer."""

    PREVIEW_MAX = 1600
    BAKE_LIMIT = 64000000

    def __init__(self, canvas):
        self.canvas = canvas
        self.active = False
        self.layer = None
        self.rect = (0.0, 0.0, 1.0, 1.0)
        self.quad = []
        self.orig_quad = []
        self.pivot = (0.0, 0.0)
        self.orig_pivot = (0.0, 0.0)
        self.mode = "free"
        self.warp = None
        self.warp_cols = 1
        self.warp_rows = 1
        self.drag = None
        self.warp_drag = None
        self.hover = None
        self.menu_open = False
        self.preview = None
        self.preview_scale = 1.0
        self.preview_box = (0.0, 0.0, 1.0, 1.0)
        self._view = None
        self._pending = False
        self._last_geo = None

    # lifecycle ----------------------------------------------------------
    def begin(self):
        """Open the transform box on the selected or top visible layer."""
        if self.active:
            return True
        layer = self.canvas.selected_layer()
        if layer is None:
            layer = self.canvas._top_visible_layer()
        if layer is None or not layer.visible or layer.image.isNull():
            return False
        if layer is not self.canvas.selected_layer():
            self.canvas.select_layer(layer)
        width = float(layer.image.width())
        height = float(layer.image.height())
        self.layer = layer
        self.rect = (layer.x, layer.y, width, height)
        self.quad = [(layer.x, layer.y),
                     (layer.x + width, layer.y),
                     (layer.x + width, layer.y + height),
                     (layer.x, layer.y + height)]
        self.orig_quad = list(self.quad)
        self.pivot = (layer.x + width * 0.5, layer.y + height * 0.5)
        self.orig_pivot = self.pivot
        self.mode = "free"
        self.warp = None
        self.warp_cols = 1
        self.warp_rows = 1
        self.drag = None
        self.warp_drag = None
        self.hover = None
        self._view = None
        self._pending = False
        self._last_geo = (list(self.quad), self.pivot, None)
        self.active = True
        self.canvas.setFocus(QtCore.Qt.FocusReason.ShortcutFocusReason)
        self.canvas.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        self._request_preview(True)
        self.canvas.update()
        return True

    def finish(self, commit=True):
        """Close the session, optionally baking the transformed layer."""
        if not self.active:
            return False
        result = None
        if commit:
            try:
                result = self._build_commit()
            except Exception:
                _log_exc("transform commit")
                result = None
        layer = self.layer
        self.active = False
        self.drag = None
        self.warp_drag = None
        self._pending = False
        self.preview = None
        self.hover = None
        self._view = None
        if result is not None and layer is not None:
            image, x, y = result
            layer.x = x
            layer.y = y
            layer.set_image(image)
        self.canvas._update_cursor()
        self.canvas.layers_changed.emit()
        self.canvas.image_changed.emit()
        self.canvas.update()
        return True

    def cancel(self):
        """Drop every transform change."""
        return self.finish(False)

    # geometry -----------------------------------------------------------
    def _build_commit(self):
        if self._unchanged():
            return None
        box = self._padded_bounds()
        image = self._map_doc(box, 1.0)
        if image is None or image.isNull():
            return None
        return image, box[0], box[1]

    def _bounds(self):
        if self.warp is not None:
            return self.warp.bounds()
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _padded_bounds(self):
        x, y, w, h = self._bounds()
        left = math.floor(min(x, x + w)) - 1.0
        top = math.floor(min(y, y + h)) - 1.0
        right = math.ceil(max(x, x + w)) + 1.0
        bottom = math.ceil(max(y, y + h)) + 1.0
        return (left, top, max(1.0, right - left),
                max(1.0, bottom - top))

    def _unchanged(self):
        if self.warp is not None:
            return False
        for i in range(4):
            if (abs(self.quad[i][0] - self.orig_quad[i][0]) > 1e-6
                    or abs(self.quad[i][1] - self.orig_quad[i][1]) > 1e-6):
                return False
        return True

    def _guard_geo(self):
        x, y, w, h = self._bounds()
        if max(1.0, abs(w)) * max(1.0, abs(h)) > self.BAKE_LIMIT:
            quad, pivot, warp = self._last_geo
            self.quad = list(quad)
            self.pivot = pivot
            self.warp = warp.clone() if warp is not None else None
            return
        self._last_geo = (list(self.quad), self.pivot,
                          self.warp.clone() if self.warp is not None
                          else None)

    # preview ------------------------------------------------------------
    def _request_preview(self, force=False):
        if not self.active:
            return
        if force:
            self._pending = False
            self._render_preview()
            return
        if self._pending:
            return
        self._pending = True
        QtCore.QTimer.singleShot(16, self._tick)

    def _tick(self):
        if not self.active or not self._pending:
            return
        self._pending = False
        self._render_preview()

    def _render_preview(self):
        if not self.active or self.layer is None:
            return
        try:
            box = self._padded_bounds()
            span = max(1.0, box[2], box[3])
            scale = min(1.0, self.PREVIEW_MAX / span)
            image = self._map_doc(box, scale)
            if image is not None and not image.isNull():
                self.preview = image
                self.preview_scale = scale
                self.preview_box = box
        except Exception:
            _log_exc("transform preview")
        self.canvas.update()

    def _map_doc(self, box, scale):
        layer = self.layer
        if layer is None or layer.image.isNull():
            return None
        width = max(1, int(math.ceil(box[2] * scale)))
        height = max(1, int(math.ceil(box[3] * scale)))
        out = QtGui.QImage(width, height,
                           QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(QtCore.Qt.GlobalColor.transparent)
        base = QtGui.QTransform()
        base.translate(-box[0] * scale, -box[1] * scale)
        base.scale(scale, scale)
        painter = QtGui.QPainter(out)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            if self.warp is not None:
                self._paint_mesh(painter, layer.image, base)
            else:
                h = rect_to_quad(
                    (0.0, 0.0, float(layer.image.width()),
                     float(layer.image.height())), self.quad)
                if h is not None:
                    painter.setTransform(qtransform(h) * base)
                painter.drawImage(QtCore.QPointF(0.0, 0.0), layer.image)
        finally:
            painter.end()
        return out

    def _paint_mesh(self, painter, image, base):
        width = float(image.width())
        height = float(image.height())
        if width <= 0.0 or height <= 0.0:
            return
        n = WARP_CELLS
        mesh = self.warp
        for j in range(n):
            t0 = j / float(n)
            t1 = (j + 1) / float(n)
            sy0 = height * t0
            sy1 = height * t1
            for i in range(n):
                s0 = i / float(n)
                s1 = (i + 1) / float(n)
                sx0 = width * s0
                sx1 = width * s1
                q = [mesh.eval(s0, t0), mesh.eval(s1, t0),
                     mesh.eval(s1, t1), mesh.eval(s0, t1)]
                src = QtCore.QRectF(sx0, sy0, sx1 - sx0, sy1 - sy0)
                if cell_flat(q):
                    hh = rect_to_quad(
                        (sx0, sy0, sx1 - sx0, sy1 - sy0), q)
                    if hh is not None:
                        painter.save()
                        try:
                            painter.setTransform(qtransform(hh) * base)
                            painter.drawImage(src, image, src)
                        finally:
                            painter.restore()
                        continue
                sp = ((sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1))
                for a, b, c in ((0, 1, 2), (0, 2, 3)):
                    hh = affine_tri((sp[a], sp[b], sp[c]),
                                    (q[a], q[b], q[c]))
                    if hh is None:
                        continue
                    xs = (sp[a][0], sp[b][0], sp[c][0])
                    ys = (sp[a][1], sp[b][1], sp[c][1])
                    sr = QtCore.QRectF(min(xs), min(ys),
                                       max(xs) - min(xs),
                                       max(ys) - min(ys))
                    if sr.width() <= 0.0 or sr.height() <= 0.0:
                        continue
                    path = QtGui.QPainterPath()
                    path.moveTo(q[a][0], q[a][1])
                    path.lineTo(q[b][0], q[b][1])
                    path.lineTo(q[c][0], q[c][1])
                    path.closeSubpath()
                    painter.save()
                    try:
                        painter.setTransform(base)
                        painter.setClipPath(
                            path, QtCore.Qt.ClipOperation.IntersectClip)
                        painter.setTransform(qtransform(hh) * base)
                        painter.drawImage(sr, image, sr)
                    finally:
                        painter.restore()

    # painting -----------------------------------------------------------
    def preview_bounds(self):
        """The document rectangle covered by the preview image."""
        return self.preview_box

    def paint_preview(self, painter, rect):
        """Draw the cached preview at the layer stack position."""
        if self.preview is None or self.preview.isNull():
            return
        b = self.preview_box
        z = self.canvas.zoom()
        target = QtCore.QRectF(rect.left() + b[0] * z,
                               rect.top() + b[1] * z,
                               b[2] * z, b[3] * z)
        painter.drawImage(target, self.preview,
                          QtCore.QRectF(self.preview.rect()))

    def refresh_cursor(self):
        """Reapply the cursor for the last hovered point."""
        if not self.active:
            return
        if self._view is None:
            self.canvas.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            return
        p = self.canvas.image_from_view(self._view)
        self._update_cursor(p.x(), p.y())

    # input --------------------------------------------------------------
    def _doc(self, event):
        p = self.canvas.image_from_view(event.position())
        return p.x(), p.y()

    def press(self, event):
        """Start a box drag, warp drag or the right-click menu."""
        if not self.active:
            return False
        self._view = event.position()
        button = event.button()
        if button == QtCore.Qt.MouseButton.RightButton:
            QtCore.QTimer.singleShot(0, self._menu)
            return True
        if button != QtCore.Qt.MouseButton.LeftButton:
            return False
        x, y = self._doc(event)
        if self.warp is not None:
            self._warp_press(x, y, event.modifiers())
        else:
            self._box_press(x, y, event.modifiers())
        return True

    def move(self, event):
        """Drag the box or warp, or update the hover cursor."""
        if not self.active:
            return False
        self._view = event.position()
        x, y = self._doc(event)
        if self.warp_drag is not None:
            self._warp_move(x, y)
        elif self.drag is not None:
            self._box_move(x, y, event.modifiers())
        else:
            self._update_cursor(x, y)
        return True

    def release(self, event):
        """Finish a box or warp drag."""
        if not self.active:
            return False
        self._view = event.position()
        x, y = self._doc(event)
        if self.warp_drag is not None:
            self._warp_move(x, y)
            self.warp_drag = None
            self._guard_geo()
            self._request_preview(False)
            self._update_cursor(x, y)
            return True
        if self.drag is not None:
            self._box_move(x, y, event.modifiers())
            g = self.drag
            self.drag = None
            if g.get("hit") == "outside":
                d = math.hypot(x - g["start"][0], y - g["start"][1])
                if d <= max(1.5, 2.0 / max(1e-6, self.canvas.zoom())):
                    self.finish(True)
                    return True
            self._update_cursor(x, y)
            return True
        return False

    def key(self, event):
        """Handle commit, cancel and nudge keys while the box is open."""
        if not self.active or self.menu_open:
            return False
        try:
            K = QtCore.Qt.Key
            key = event.key()
            mods = event.modifiers()
            ctrl = bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & QtCore.Qt.KeyboardModifier.ShiftModifier)
            if key in (K.Key_Return, K.Key_Enter):
                self.finish(True)
                return True
            if key == K.Key_Escape or (key == K.Key_Z and ctrl):
                self.finish(False)
                return True
            step = 10.0 if shift else 1.0
            dx = dy = 0.0
            if key == K.Key_Left:
                dx = -step
            elif key == K.Key_Right:
                dx = step
            elif key == K.Key_Up:
                dy = -step
            elif key == K.Key_Down:
                dy = step
            if dx != 0.0 or dy != 0.0:
                if self.warp is not None:
                    self.warp = self.warp.map_points(
                        lambda p: (p[0] + dx, p[1] + dy))
                else:
                    self.quad = [(p[0] + dx, p[1] + dy)
                                 for p in self.quad]
                    self.pivot = (self.pivot[0] + dx, self.pivot[1] + dy)
                self._guard_geo()
                self._request_preview(True)
                return True
            return False
        except Exception:
            _log_exc("transform key")
            return False

    def _hit(self, x, y):
        tol = max(1.25, HIT_PX / max(1e-6, self.canvas.zoom()))
        best = None
        for i in range(4):
            q = self.quad[i]
            d = math.hypot(q[0] - x, q[1] - y)
            if d < tol and (best is None or d < best[0]):
                best = (d, ("corner", i))
        for i in range(4):
            a = self.quad[i]
            b = self.quad[(i + 1) % 4]
            q = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            d = math.hypot(q[0] - x, q[1] - y)
            if d < tol and (best is None or d < best[0]):
                best = (d, ("edge", i))
        d = math.hypot(self.pivot[0] - x, self.pivot[1] - y)
        if d < tol and (best is None or d < best[0]):
            best = (d, "pivot")
        if best is not None:
            return best[1]
        return "inside" if quad_inside(self.quad, (x, y)) else "outside"

    @staticmethod
    def _mode_allows(mode, hit):
        if mode == "distort":
            return not (hit == "outside"
                        or (isinstance(hit, tuple) and hit[0] == "edge"))
        if mode == "skew":
            return hit != "outside"
        return True

    @staticmethod
    def _mod_dict(mods):
        return {
            "ctrl": bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier),
            "shift": bool(mods & QtCore.Qt.KeyboardModifier.ShiftModifier),
            "alt": bool(mods & QtCore.Qt.KeyboardModifier.AltModifier),
            "meta": bool(mods & QtCore.Qt.KeyboardModifier.MetaModifier),
        }

    def _update_cursor(self, x, y):
        if not self.active:
            return
        B = QtCore.Qt.CursorShape
        if self.warp is not None:
            hit = self._warp_hit(x, y)
            self.hover = hit
            if hit is not None or quad_inside(self.quad, (x, y)):
                self.canvas.setCursor(B.SizeAllCursor)
            else:
                self.canvas.setCursor(B.ArrowCursor)
            return
        h = self._hit(x, y)
        self.hover = h
        if h == "outside":
            shape = B.CrossCursor
        elif h in ("inside", "pivot"):
            shape = B.SizeAllCursor
        elif h[0] == "corner":
            shape = (B.SizeFDiagCursor if h[1] in (0, 2)
                     else B.SizeBDiagCursor)
        else:
            shape = (B.SizeVerCursor if h[1] in (0, 2)
                     else B.SizeHorCursor)
        self.canvas.setCursor(shape)

    def _box_press(self, x, y, mods):
        m = self._mod_dict(mods)
        hit = self._hit(x, y)
        if m["alt"] and hit in ("inside", "outside"):
            self.pivot = (x, y)
            hit = "pivot"
        if hit != "outside" and not self._mode_allows(self.mode, hit):
            self.drag = None
            return
        self.drag = dict(hit=hit, start=(x, y), quad0=list(self.quad),
                         pivot0=self.pivot, mode=self.mode)

    def _box_move(self, x, y, mods):
        g = self.drag
        if g is None:
            return
        if (g["hit"] != "outside"
                and not self._mode_allows(g["mode"], g["hit"])):
            return
        m = self._mod_dict(mods)
        self._apply_mode_drag(g, x, y, g["mode"], m)
        self._guard_geo()
        self._request_preview(False)

    def _apply_mode_drag(self, g, x, y, mode, m):
        hit = g["hit"]
        if not self._mode_allows(mode, hit):
            return
        if (mode == "skew" and isinstance(hit, tuple)
                and hit[0] == "corner"):
            self._skew_corner(g, x, y, m)
            return
        if (mode == "rotate" and isinstance(hit, tuple)
                and hit[0] in ("corner", "edge")):
            self._apply_drag(g, "outside", x, y, m)
            return
        if (mode == "skew" and isinstance(hit, tuple)
                and hit[0] == "edge"):
            m = dict(m)
            m["ctrl"] = True
            m["shift"] = True
            self._apply_drag(g, hit, x, y, m)
            return
        self._apply_drag(g, hit, x, y, self._mode_mods(mode, hit, m))

    @staticmethod
    def _mode_mods(mode, hit, m):
        m = dict(m)
        if isinstance(hit, tuple) and hit[0] == "corner":
            if mode == "distort":
                m["ctrl"] = True
            elif mode == "perspective":
                m["ctrl"] = True
                m["alt"] = True
                m["shift"] = True
        return m

    def _skew_corner(self, g, x, y, m):
        quad0 = g["quad0"]
        i = g["hit"][1]
        dx = x - g["start"][0]
        dy = y - g["start"][1]

        def along(j):
            ex = quad0[i][0] - quad0[j][0]
            ey = quad0[i][1] - quad0[j][1]
            ln = math.hypot(ex, ey)
            ux, uy = (ex / ln, ey / ln) if ln > 0.0 else (0.0, 0.0)
            t = dx * ux + dy * uy
            return (t * ux, t * uy)
        hn = (1, 0, 3, 2)[i]
        vn = (3, 2, 1, 0)[i]
        h = along(hn)
        v = along(vn)
        mm = (h if math.hypot(h[0], h[1]) >= math.hypot(v[0], v[1])
              else v)
        q = list(quad0)
        for k in range(4):
            if k == i:
                sign = 1.0
            elif m["alt"] and k == (i + 2) % 4:
                sign = -1.0
            else:
                continue
            q[k] = (quad0[k][0] + sign * mm[0],
                    quad0[k][1] + sign * mm[1])
        self.quad = keep_convex(quad0, q)
        self.pivot = self._carry_pivot(quad0, self.quad, g["pivot0"])

    @staticmethod
    def _carry_pivot(quad0, quad, pivot0):
        h0 = rect_to_quad((0.0, 0.0, 1.0, 1.0), quad0)
        h1 = rect_to_quad((0.0, 0.0, 1.0, 1.0), quad)
        if h0 is None or h1 is None:
            return pivot0
        inv = h_inv(h0)
        if inv is None:
            return pivot0
        uv = h_apply(inv, pivot0[0], pivot0[1])
        if uv is None:
            return pivot0
        xy = h_apply(h1, uv[0], uv[1])
        if xy is None:
            return pivot0
        return xy

    def _apply_drag(self, g, hit, x, y, m):
        start = g["start"]
        quad0 = g["quad0"]
        pivot0 = g["pivot0"]
        dx = x - start[0]
        dy = y - start[1]
        if hit == "inside":
            if m["shift"]:
                prev = (self.quad[0][0] - quad0[0][0],
                        self.quad[0][1] - quad0[0][1])
                dx, dy = constrain(dx, dy, prev)
            self.quad = [(q[0] + dx, q[1] + dy) for q in quad0]
            self.pivot = (pivot0[0] + dx, pivot0[1] + dy)
            return
        if hit == "pivot":
            self.pivot = (x, y)
            return
        if hit == "outside":
            a0 = math.atan2(start[1] - pivot0[1], start[0] - pivot0[0])
            a1 = math.atan2(y - pivot0[1], x - pivot0[0])
            da = a1 - a0
            if m["shift"]:
                base = math.atan2(quad0[1][1] - quad0[0][1],
                                  quad0[1][0] - quad0[0][0])
                step = math.radians(15.0)
                da = round((base + da) / step) * step - base
            sn, cs = math.sin(da), math.cos(da)
            cx, cy = pivot0
            q = []
            for px, py in quad0:
                ox, oy = px - cx, py - cy
                q.append((cx + ox * cs - oy * sn,
                          cy + ox * sn + oy * cs))
            self.quad = q
            return
        if isinstance(hit, tuple) and hit[0] == "corner":
            i = hit[1]
            if m["ctrl"] and m["alt"] and m["shift"]:
                horizontal = abs(dx) >= abs(dy)
                j = {(0, True): 1, (1, True): 0, (2, True): 3,
                     (3, True): 2, (0, False): 3, (3, False): 0,
                     (1, False): 2}.get((i, horizontal), 1)
                mx, my = (dx, 0.0) if horizontal else (0.0, dy)
                q = list(quad0)
                q[i] = (quad0[i][0] + mx, quad0[i][1] + my)
                q[j] = (quad0[j][0] - mx, quad0[j][1] - my)
                self.quad = keep_convex(quad0, q)
                self.pivot = self._carry_pivot(quad0, self.quad,
                                               pivot0)
                return
            if m["ctrl"]:
                q = list(quad0)
                q[i] = (quad0[i][0] + dx, quad0[i][1] + dy)
                self.quad = keep_convex(quad0, q)
                self.pivot = self._carry_pivot(quad0, self.quad,
                                               pivot0)
                return
        elif isinstance(hit, tuple) and hit[0] == "edge":
            i = hit[1]
            if m["ctrl"]:
                a, b = i, (i + 1) % 4
                mx, my = dx, dy
                if m["shift"]:
                    ex = quad0[b][0] - quad0[a][0]
                    ey = quad0[b][1] - quad0[a][1]
                    l2 = ex * ex + ey * ey
                    t = ((dx * ex + dy * ey) / l2) if l2 > 0.0 else 0.0
                    mx, my = t * ex, t * ey
                q = list(quad0)
                q[a] = (quad0[a][0] + mx, quad0[a][1] + my)
                q[b] = (quad0[b][0] + mx, quad0[b][1] + my)
                if m["alt"]:
                    c, d = (i + 2) % 4, (i + 3) % 4
                    q[c] = (quad0[c][0] - mx, quad0[c][1] - my)
                    q[d] = (quad0[d][0] - mx, quad0[d][1] - my)
                self.quad = q
                self.pivot = self._carry_pivot(quad0, self.quad,
                                               pivot0)
                return
        if not isinstance(hit, tuple):
            return
        self._scale_drag(quad0, pivot0, hit, x, y, m)

    def _scale_drag(self, quad0, pivot0, hit, x, y, m):
        h = rect_to_quad((0.0, 0.0, 1.0, 1.0), quad0)
        if h is None:
            return
        inv = h_inv(h)
        if inv is None:
            return
        uv = h_apply(inv, x, y)
        puv = h_apply(inv, pivot0[0], pivot0[1])
        if uv is None or puv is None:
            return
        u, v = uv
        pu, pv = puv
        if hit[0] == "corner":
            mu = ((True, False) if hit[1] == 0 else
                  (False, True) if hit[1] == 1 else
                  (False, True) if hit[1] == 2 else
                  (True, False))
            mv = ((True, False) if hit[1] == 0 else
                  (True, False) if hit[1] == 1 else
                  (False, True) if hit[1] == 2 else
                  (False, True))
        else:
            mu = ((False, False) if hit[1] in (0, 2) else
                  (False, True) if hit[1] == 1 else
                  (True, False))
            mv = ((True, False) if hit[1] in (0, 2) else
                  (False, False))

        def axis(moving, at, pv0):
            if not moving[0] and not moving[1]:
                return (0.5, 1.0)
            handle = 0.0 if moving[0] else 1.0
            anchor = pv0 if m["alt"] else 1.0 - handle
            d = handle - anchor
            k = ((at - anchor) / d) if abs(d) > 1e-9 else 1.0
            if k != k or abs(k) > 1e12:
                k = 1.0
            return (anchor, k)
        au, ku = axis(mu, u, pu)
        av, kv = axis(mv, v, pv)
        corner = hit[0] == "corner"
        if not corner and not m["shift"]:
            if mu[0] or mu[1]:
                av = pv if m["alt"] else 0.5
                kv = abs(ku)
            else:
                au = pu if m["alt"] else 0.5
                ku = abs(kv)
        if corner and not m["shift"]:
            k = max(abs(ku), abs(kv))
            ku = k * (1.0 if ku >= 0.0 else -1.0)
            kv = k * (1.0 if kv >= 0.0 else -1.0)
        r = (au - au * ku, av - av * kv,
             au + (1.0 - au) * ku, av + (1.0 - av) * kv)

        def mapuv(a, b):
            p = h_apply(h, a, b)
            return p if p is not None else (0.0, 0.0)
        self.quad = [mapuv(r[0], r[1]), mapuv(r[2], r[1]),
                     mapuv(r[2], r[3]), mapuv(r[0], r[3])]
        if m["alt"]:
            self.pivot = pivot0
        else:
            self.pivot = self._carry_pivot(quad0, self.quad, pivot0)

    # warp ---------------------------------------------------------------
    def _warp_hit(self, x, y):
        m = self.warp
        if m is None:
            return None
        tol = max(1.25, HIT_PX / max(1e-6, self.canvas.zoom()))
        nx = m.nx()
        best = None
        for idx, p in enumerate(m.points):
            i = idx % nx
            j = idx // nx
            if i % 3 != 0 and j % 3 != 0:
                continue
            d = math.hypot(p[0] - x, p[1] - y)
            if d < tol and (best is None or d < best[0]):
                best = (d, idx)
        return None if best is None else best[1]

    def _warp_press(self, x, y, mods):
        m = self.warp
        if m is None:
            return
        idx = self._warp_hit(x, y)
        if idx is not None:
            self.warp_drag = dict(kind="point", index=idx, start=(x, y),
                                  pts0=list(m.points))
            return
        s, t = m.param_at((x, y))
        q = m.eval(s, t)
        tol = max(2.0, HIT_PX / max(1e-6, self.canvas.zoom()))
        if math.hypot(q[0] - x, q[1] - y) <= tol:
            self.warp_drag = dict(kind="surface", s=s, t=t,
                                  start=(x, y), pts0=list(m.points))

    def _warp_move(self, x, y):
        d = self.warp_drag
        if d is None or self.warp is None:
            return
        dx = x - d["start"][0]
        dy = y - d["start"][1]
        try:
            if d["kind"] == "point":
                self.warp.drag_point(d["pts0"], d["index"], (dx, dy))
            else:
                self.warp.pull(d["pts0"], d["s"], d["t"], (dx, dy))
        except Exception:
            _log_exc("transform warp drag")

    def toggle_warp(self):
        """Turn the warp mesh on or off."""
        if not self.active:
            return
        if self.warp is not None:
            self.warp = None
        else:
            self._ensure_warp()
        self._request_preview(True)

    def _ensure_warp(self):
        if self.warp is None:
            self.warp = WarpMesh.from_quad(
                self.quad, self.warp_cols, self.warp_rows)

    def reset_warp(self):
        """Rebuild the warp mesh from the current box."""
        if not self.active:
            return
        self.warp = WarpMesh.from_quad(
            self.quad, self.warp_cols, self.warp_rows)
        self._request_preview(True)

    def set_warp_grid(self, cols, rows):
        """Set the warp grid resolution."""
        self.warp_cols = max(1, min(4, int(cols)))
        self.warp_rows = max(1, min(4, int(rows)))
        if self.active and self.warp is not None:
            self.warp = WarpMesh.from_quad(
                self.quad, self.warp_cols, self.warp_rows)
            self._request_preview(True)

    # menu and modes -----------------------------------------------------
    def _menu(self):
        if not self.active:
            return
        try:
            menu = QtWidgets.QMenu(self.canvas)
            for label, mode, check in (
                    ("Free Transform", "free",
                     self.mode == "free" and self.warp is None),
                    ("Rotate", "rotate",
                     self.mode == "rotate" and self.warp is None),
                    ("Skew", "skew",
                     self.mode == "skew" and self.warp is None),
                    ("Distort", "distort",
                     self.mode == "distort" and self.warp is None),
                    ("Perspective", "perspective",
                     self.mode == "perspective" and self.warp is None)):
                a = menu.addAction(label)
                a.setCheckable(True)
                a.setChecked(bool(check))
                a.triggered.connect(
                    lambda *_x, m=mode: self.set_mode(m))
            menu.addSeparator()
            aw = menu.addAction("Warp")
            aw.setCheckable(True)
            aw.setChecked(self.warp is not None)
            aw.triggered.connect(lambda *_x: self.toggle_warp())
            arw = menu.addAction("Reset Warp")
            arw.setEnabled(self.warp is not None)
            arw.triggered.connect(lambda *_x: self.reset_warp())
            wg = menu.addMenu("Warp Grid")
            for c, r, name in ((1, 1, "1 x 1 (Default)"),
                               (2, 2, "2 x 2"), (3, 3, "3 x 3"),
                               (4, 4, "4 x 4")):
                a = wg.addAction(name)
                a.setCheckable(True)
                a.setChecked(self.warp_cols == c and self.warp_rows == r)
                a.triggered.connect(
                    lambda *_x, cc=c, rr=r: self.set_warp_grid(cc, rr))
            menu.addSeparator()
            a = menu.addAction("Flip Horizontal")
            a.triggered.connect(lambda *_x: self.flip(True))
            a = menu.addAction("Flip Vertical")
            a.triggered.connect(lambda *_x: self.flip(False))
            menu.addSeparator()
            a = menu.addAction("Rotate 90 CW")
            a.triggered.connect(lambda *_x: self.rotate90(True))
            a = menu.addAction("Rotate 90 CCW")
            a.triggered.connect(lambda *_x: self.rotate90(False))
            a = menu.addAction("Rotate 180")
            a.triggered.connect(lambda *_x: self.rotate180())
            menu.addSeparator()
            a = menu.addAction("Reset Transform")
            a.triggered.connect(lambda *_x: self.reset())
            self.menu_open = True
            try:
                menu.exec(QtGui.QCursor.pos())
            finally:
                self.menu_open = False
                menu.deleteLater()
        except Exception:
            self.menu_open = False
            _log_exc("transform menu")

    def set_mode(self, mode):
        """Switch between free, rotate, skew, distort and perspective."""
        if not self.active:
            return
        self.warp = None
        self.mode = mode
        self._request_preview(True)

    def _map_geo(self, fn):
        if self.warp is not None:
            self.warp = self.warp.map_points(fn)
        else:
            self.quad = [fn(p) for p in self.quad]

    def flip(self, horizontal):
        """Mirror the box or warp around the pivot."""
        if not self.active:
            return
        px, py = self.pivot
        if horizontal:
            self._map_geo(lambda p: (2.0 * px - p[0], p[1]))
        else:
            self._map_geo(lambda p: (p[0], 2.0 * py - p[1]))
        self._guard_geo()
        self._request_preview(True)

    def _rotate_geo(self, deg):
        a = math.radians(deg)
        sn, cs = math.sin(a), math.cos(a)
        cx, cy = self.pivot

        def fn(p):
            x, y = p[0] - cx, p[1] - cy
            return (cx + x * cs - y * sn, cy + x * sn + y * cs)
        self._map_geo(fn)
        self._guard_geo()
        self._request_preview(True)

    def rotate90(self, cw):
        """Rotate the box or warp by 90 degrees."""
        if self.active:
            self._rotate_geo(90.0 if cw else -90.0)

    def rotate180(self):
        """Rotate the box or warp by 180 degrees."""
        if self.active:
            self._rotate_geo(180.0)

    def reset(self):
        """Restore the original box and drop the warp."""
        if not self.active:
            return
        self.quad = list(self.orig_quad)
        self.pivot = self.orig_pivot
        self.warp = None
        self.mode = "free"
        self._last_geo = (list(self.quad), self.pivot, None)
        self._request_preview(True)

    # overlay ------------------------------------------------------------
    def paint_overlay(self, painter):
        """Paint the transform box or warp mesh over the canvas."""
        draw_overlay(self, painter)
