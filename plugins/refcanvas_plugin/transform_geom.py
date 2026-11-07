"""Homography, quad and Bezier warp geometry for the REFCANVAS transform."""
from __future__ import annotations

import math

try:
    from .common import _qt
except ImportError:
    from common import _qt

QtCore, QtGui, QtWidgets = _qt()

HANDLE_PX = 7.0
HIT_PX = 8.0
WARP_CELLS = 24

BERN_INV = ((1.0, 0.0, 0.0, 0.0),
            (-5.0 / 6.0, 3.0, -1.5, 1.0 / 3.0),
            (1.0 / 3.0, -1.5, 3.0, -5.0 / 6.0),
            (0.0, 0.0, 0.0, 1.0))


def finite(value):
    """True for a usable finite number."""
    try:
        return (value is not None and value == value
                and abs(float(value)) < 1e12)
    except Exception:
        return False


def bern(t):
    """Cubic Bernstein weights."""
    s = 1.0 - t
    return (s * s * s, 3.0 * s * s * t, 3.0 * s * t * t, t * t * t)


def quad_inside(quad, point):
    """Even-odd point-in-quad test."""
    x, y = float(point[0]), float(point[1])
    inside = False
    j = 3
    for i in range(4):
        ax, ay = quad[j]
        bx, by = quad[i]
        if ((ay > y) != (by > y)) and (
                x < (bx - ax) * (y - ay) / (by - ay) + ax):
            inside = not inside
        j = i
    return inside


def quad_turns(quad):
    """Cross products at each quad corner."""
    out = []
    for k in range(4):
        ax, ay = quad[k]
        bx, by = quad[(k + 1) % 4]
        cx, cy = quad[(k + 2) % 4]
        out.append((bx - ax) * (cy - by) - (by - ay) * (cx - bx))
    return out


def convex(quad, sign, min_turn):
    """True when every corner keeps the given turn direction."""
    try:
        return all(t * sign > min_turn for t in quad_turns(quad))
    except Exception:
        return False


def keep_convex(frm, to):
    """Clamp a quad edit so it never folds over."""
    try:
        turns = quad_turns(frm)
        sign = 1.0 if turns[0] >= 0 else -1.0
        min_turn = min(abs(t) for t in turns) * 1e-3
        if not (finite(min_turn) and min_turn > 0.0
                and convex(frm, sign, 0.0)):
            return to
        if convex(to, sign, min_turn):
            return to

        def lerp(t):
            return [(frm[k][0] + (to[k][0] - frm[k][0]) * t,
                     frm[k][1] + (to[k][1] - frm[k][1]) * t)
                    for k in range(4)]
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) * 0.5
            if convex(lerp(mid), sign, min_turn):
                lo = mid
            else:
                hi = mid
        return lerp(lo)
    except Exception:
        return to


def square_to_quad(quad):
    """Unit square to TL, TR, BR, BL quad homography (row major)."""
    try:
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
        sx = x0 - x1 + x2 - x3
        sy = y0 - y1 + y2 - y3
        if abs(sx) < 1e-12 and abs(sy) < 1e-12:
            return (x1 - x0, x3 - x0, x0,
                    y1 - y0, y3 - y0, y0,
                    0.0, 0.0, 1.0)
        dx1, dx2 = x1 - x2, x3 - x2
        dy1, dy2 = y1 - y2, y3 - y2
        den = dx1 * dy2 - dx2 * dy1
        if abs(den) < 1e-12:
            return None
        g = (sx * dy2 - dx2 * sy) / den
        h = (dx1 * sy - sx * dy1) / den
        return (x1 - x0 + g * x1, x3 - x0 + h * x3, x0,
                y1 - y0 + g * y1, y3 - y0 + h * y3, y0,
                g, h, 1.0)
    except Exception:
        return None


def h_apply(h, x, y):
    """Apply a row-major homography."""
    w = h[6] * x + h[7] * y + h[8]
    if abs(w) < 1e-12:
        return None
    return ((h[0] * x + h[1] * y + h[2]) / w,
            (h[3] * x + h[4] * y + h[5]) / w)


def h_mul(a, b):
    """Multiply two row-major homographies."""
    out = [0.0] * 9
    for i in range(3):
        for j in range(3):
            out[i * 3 + j] = (a[i * 3] * b[j]
                              + a[i * 3 + 1] * b[3 + j]
                              + a[i * 3 + 2] * b[6 + j])
    return tuple(out)


def h_inv(m):
    """Invert a row-major homography, or None."""
    c = (m[4] * m[8] - m[5] * m[7],
         m[2] * m[7] - m[1] * m[8],
         m[1] * m[5] - m[2] * m[4],
         m[5] * m[6] - m[3] * m[8],
         m[0] * m[8] - m[2] * m[6],
         m[2] * m[3] - m[0] * m[5],
         m[3] * m[7] - m[4] * m[6],
         m[1] * m[6] - m[0] * m[7],
         m[0] * m[4] - m[1] * m[3])
    det = m[0] * c[0] + m[1] * c[3] + m[2] * c[6]
    if abs(det) < 1e-12:
        return None
    return tuple(v / det for v in c)


def rect_to_quad(rect, quad):
    """Map a source rectangle in document pixels onto a quad."""
    try:
        x, y, w, h = (float(rect[0]), float(rect[1]),
                      float(rect[2]), float(rect[3]))
        if w == 0.0 or h == 0.0:
            return None
        hq = square_to_quad(quad)
        if hq is None:
            return None
        to_unit = (1.0 / w, 0.0, -x / w,
                   0.0, 1.0 / h, -y / h,
                   0.0, 0.0, 1.0)
        return h_mul(hq, to_unit)
    except Exception:
        return None


def qtransform(h):
    """Convert a row-major homography to a QTransform."""
    if h is None:
        return QtGui.QTransform()
    return QtGui.QTransform(h[0], h[3], h[6],
                            h[1], h[4], h[7],
                            h[2], h[5], h[8])


def cell_flat(quad):
    """True when a mesh cell is convex enough for a projective map."""
    try:
        turns = quad_turns(quad)
        if not all(finite(v) for v in turns):
            return False
        if all(v > 1e-7 for v in turns):
            return True
        return all(v < -1e-7 for v in turns)
    except Exception:
        return False


def affine_tri(src, dst):
    """Affine map from a source triangle to a destination triangle."""
    try:
        (x0, y0), (x1, y1), (x2, y2) = src
        (u0, v0), (u1, v1), (u2, v2) = dst
        det = x0 * (y1 - y2) - y0 * (x1 - x2) + (x1 * y2 - x2 * y1)
        if not finite(det) or abs(det) < 1e-12:
            return None
        i00 = (y1 - y2) / det
        i01 = (y2 - y0) / det
        i02 = (y0 - y1) / det
        i10 = (x2 - x1) / det
        i11 = (x0 - x2) / det
        i12 = (x1 - x0) / det
        i20 = (x1 * y2 - x2 * y1) / det
        i21 = (x2 * y0 - x0 * y2) / det
        i22 = (x0 * y1 - x1 * y0) / det
        return (u0 * i00 + u1 * i01 + u2 * i02,
                u0 * i10 + u1 * i11 + u2 * i12,
                u0 * i20 + u1 * i21 + u2 * i22,
                v0 * i00 + v1 * i01 + v2 * i02,
                v0 * i10 + v1 * i11 + v2 * i12,
                v0 * i20 + v1 * i21 + v2 * i22,
                0.0, 0.0, 1.0)
    except Exception:
        return None


def constrain(dx, dy, prev=None, n=8):
    """Eight-direction move lock with hysteresis."""
    length = math.hypot(dx, dy)
    if n <= 0 or length <= 0.0 or length != length:
        return dx, dy
    step = 2.0 * math.pi / n
    angle = math.atan2(dy, dx)
    k = round(angle / step)
    if prev is not None:
        pl = math.hypot(prev[0], prev[1])
        if pl > 0.0:
            kp = round(math.atan2(prev[1], prev[0]) / step)
            off = (angle - kp * step) % (2.0 * math.pi)
            off = min(off, 2.0 * math.pi - off)
            if off < step * 0.5 + math.radians(8.0):
                k = kp
    ca, sa = math.cos(k * step), math.sin(k * step)
    t = max(0.0, dx * ca + dy * sa)
    rx, ry = t * ca, t * sa
    if abs(rx) < 1e-9:
        rx = 0.0
    if abs(ry) < 1e-9:
        ry = 0.0
    return rx, ry


class WarpMesh:
    """A grid of cubic Bezier patches over the unit square."""

    def __init__(self, us, vs, points):
        self.us = [float(v) for v in us]
        self.vs = [float(v) for v in vs]
        self.points = [(float(p[0]), float(p[1])) for p in points]

    @staticmethod
    def fit(us, vs, fn):
        """Fit Bezier control points to a sampled warp function."""
        pc = len(us) - 1
        pr = len(vs) - 1
        nx = 3 * pc + 1
        ny = 3 * pr + 1
        pts = [(0.0, 0.0)] * (nx * ny)
        for pj in range(pr):
            for pi in range(pc):
                samp = [[None] * 4 for _ in range(4)]
                for j in range(4):
                    for i in range(4):
                        u = us[pi] + (us[pi + 1] - us[pi]) * i / 3.0
                        t = vs[pj] + (vs[pj + 1] - vs[pj]) * j / 3.0
                        samp[j][i] = fn(u, t)
                for j in range(4):
                    for i in range(4):
                        ax = ay = 0.0
                        for a in range(4):
                            wa = BERN_INV[j][a]
                            if wa == 0.0:
                                continue
                            for b in range(4):
                                wb = BERN_INV[i][b]
                                if wb == 0.0:
                                    continue
                                k = wa * wb
                                ax += k * samp[a][b][0]
                                ay += k * samp[a][b][1]
                        pts[(3 * pj + j) * nx + 3 * pi + i] = (ax, ay)
        return WarpMesh(us, vs, pts)

    @staticmethod
    def identity(rect, cols=1, rows=1):
        """An unwarped mesh spanning a document rectangle."""
        cols = max(1, min(64, int(cols)))
        rows = max(1, min(64, int(rows)))
        us = [i / float(cols) for i in range(cols + 1)]
        vs = [j / float(rows) for j in range(rows + 1)]
        x, y, w, h = rect
        return WarpMesh.fit(us, vs, lambda s, t: (x + s * w, y + t * h))

    @staticmethod
    def from_quad(quad, cols=1, rows=1):
        """A mesh that follows a projective quad."""
        cols = max(1, min(64, int(cols)))
        rows = max(1, min(64, int(rows)))
        us = [i / float(cols) for i in range(cols + 1)]
        vs = [j / float(rows) for j in range(rows + 1)]
        hq = square_to_quad(quad)
        if hq is None:
            return WarpMesh.identity(
                (quad[0][0], quad[0][1], quad[1][0] - quad[0][0],
                 quad[3][1] - quad[0][1]), cols, rows)

        def f(s, t):
            p = h_apply(hq, s, t)
            return p if p is not None else (0.0, 0.0)
        return WarpMesh.fit(us, vs, f)

    def clone(self):
        """A copy that shares no point data."""
        return WarpMesh(self.us, self.vs, self.points)

    def nx(self):
        """Point columns."""
        return 3 * (len(self.us) - 1) + 1

    def ny(self):
        """Point rows."""
        return 3 * (len(self.vs) - 1) + 1

    def point(self, i, j):
        """One control point."""
        return self.points[j * self.nx() + i]

    def map_points(self, fn):
        """Apply a point function to every control point."""
        return WarpMesh(self.us, self.vs, [fn(p) for p in self.points])

    def scaled(self, sx, sy):
        """Scale every control point."""
        return self.map_points(lambda p: (p[0] * sx, p[1] * sy))

    @staticmethod
    def _locate(knots, s):
        n = len(knots) - 1
        s = max(0.0, min(1.0, s))
        i = 0
        while i + 1 < n and s > knots[i + 1]:
            i += 1
        w = knots[i + 1] - knots[i]
        return i, ((s - knots[i]) / w if w > 0.0 else 0.0)

    def eval(self, s, t):
        """Evaluate the surface at unit coordinates."""
        pi, a = self._locate(self.us, s)
        pj, b = self._locate(self.vs, t)
        ba = bern(a)
        bb = bern(b)
        nx = self.nx()
        px = py = 0.0
        for j in range(4):
            wb = bb[j]
            if wb == 0.0:
                continue
            row = (3 * pj + j) * nx + 3 * pi
            for i in range(4):
                wa = ba[i]
                if wa == 0.0:
                    continue
                p = self.points[row + i]
                k = wa * wb
                px += p[0] * k
                py += p[1] * k
        return (px, py)

    def param_at(self, p):
        """Nearest unit coordinates to a document point."""
        n = 48
        bs = bt = 0.5
        best = 1e300
        for j in range(n + 1):
            t = j / float(n)
            for i in range(n + 1):
                s = i / float(n)
                q = self.eval(s, t)
                d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
                if d < best:
                    best = d
                    bs, bt = s, t
        s, t = bs, bt
        h = 1e-5
        for _ in range(12):
            q = self.eval(s, t)
            qs = self.eval(s + h, t)
            qt = self.eval(s, t + h)
            a = (qs[0] - q[0]) / h
            b = (qt[0] - q[0]) / h
            c = (qs[1] - q[1]) / h
            d = (qt[1] - q[1]) / h
            det = a * d - b * c
            if abs(det) < 1e-12:
                break
            ex = p[0] - q[0]
            ey = p[1] - q[1]
            s = max(0.0, min(1.0, s + (d * ex - b * ey) / det))
            t = max(0.0, min(1.0, t + (a * ey - c * ex) / det))
        return s, t

    def _smooth_lines(self, i0, i1, j0, j1):
        """Smooth control point rows and columns after a pull."""
        nx = self.nx()
        ny = self.ny()
        i1 = min(i1, nx)
        j1 = min(j1, ny)

        def hu(k):
            return self.us[k + 1] - self.us[k]

        def hv(k):
            return self.vs[k + 1] - self.vs[k]
        triples = []
        for a in range(1, len(self.us) - 1):
            if 3 * a >= i0 and 3 * a < i1:
                for j in range(j0, j1):
                    triples.append((j * nx + 3 * a - 1, j * nx + 3 * a,
                                    j * nx + 3 * a + 1, hu(a - 1), hu(a)))
        for b in range(1, len(self.vs) - 1):
            if 3 * b >= j0 and 3 * b < j1:
                for i in range(i0, i1):
                    triples.append(((3 * b - 1) * nx + i,
                                    3 * b * nx + i,
                                    (3 * b + 1) * nx + i,
                                    hv(b - 1), hv(b)))
        for l, c, r, hl, hr in triples:
            pl = self.points[l]
            pc = self.points[c]
            pr = self.points[r]
            tx = ((pc[0] - pl[0]) / hl + (pr[0] - pc[0]) / hr) / 2.0
            ty = ((pc[1] - pl[1]) / hl + (pr[1] - pc[1]) / hr) / 2.0
            self.points[l] = (pc[0] - tx * hl, pc[1] - ty * hl)
            self.points[r] = (pc[0] + tx * hr, pc[1] + ty * hr)

    def pull(self, base, s, t, d):
        """Drag the surface at unit coordinates by a document delta."""
        border_zone = 0.12
        reach_scale = 1.8
        if len(base) != len(self.points):
            return
        if not (finite(d[0]) and finite(d[1])):
            return
        self.points = list(base)
        cols = len(self.us) - 1
        rows = len(self.vs) - 1
        pi, a = self._locate(self.us, s)
        pj, b = self._locate(self.vs, t)
        ba = bern(a)
        bb = bern(b)
        nx = self.nx()
        ny = self.ny()

        def anchor(ai, aj):
            return base[3 * aj * nx + 3 * ai]
        at0 = self.eval(s, t)
        target = (at0[0] + d[0], at0[1] + d[1])
        size = 1.0
        for k in (0, 1):
            vals = (anchor(pi, pj)[k], anchor(pi + 1, pj)[k],
                    anchor(pi, pj + 1)[k], anchor(pi + 1, pj + 1)[k])
            size = max(size, max(vals) - min(vals))
        radius = reach_scale * size
        inner_w = (ba[1] + ba[2]) * (bb[1] + bb[2])
        interior = max(0.0, min(1.0, inner_w / 0.5625))
        to_border = min(s, 1.0 - s, t, 1.0 - t)
        near_border = max(0.0, min(1.0, 1.0 - to_border / border_zone))

        def mesh_corner(ai, aj):
            return (ai == 0 or ai == cols) and (aj == 0 or aj == rows)

        def reach(ai, aj, wa, wb):
            border = ai == 0 or ai == cols or aj == 0 or aj == rows
            if mesh_corner(ai, aj):
                return 0.0
            return wa * wb * (near_border if border else 1.0)
        corner = [
            (pi, pj, reach(pi, pj, ba[0] + ba[1], bb[0] + bb[1])),
            (pi + 1, pj, reach(pi + 1, pj, ba[2] + ba[3],
                               bb[0] + bb[1])),
            (pi, pj + 1, reach(pi, pj + 1, ba[0] + ba[1],
                               bb[2] + bb[3])),
            (pi + 1, pj + 1, reach(pi + 1, pj + 1, ba[2] + ba[3],
                                   bb[2] + bb[3])),
        ]
        share = [0.0] * ((cols + 1) * (rows + 1))
        for aj in range(rows + 1):
            for ai in range(cols + 1):
                p = anchor(ai, aj)
                x = math.hypot(p[0] - at0[0], p[1] - at0[1]) / radius
                x = max(0.0, min(1.0, x))
                fall = 0.5 * (1.0 + math.cos(math.pi * x))
                border = ai == 0 or ai == cols or aj == 0 or aj == rows
                if mesh_corner(ai, aj):
                    edge = 0.0
                elif border:
                    edge = near_border
                else:
                    edge = 1.0
                share[aj * (cols + 1) + ai] = fall * edge
        for ai, aj, w in corner:
            idx = aj * (cols + 1) + ai
            share[idx] = max(share[idx], (1.0 - interior) * w)
        for j in range(ny):
            for i in range(nx):
                ai = min((i + 1) // 3, cols)
                aj = min((j + 1) // 3, rows)
                k = share[aj * (cols + 1) + ai]
                p = self.points[j * nx + i]
                self.points[j * nx + i] = (p[0] + d[0] * k,
                                           p[1] + d[1] * k)
        norm = 0.0
        for j in (1, 2):
            for i in (1, 2):
                norm += (ba[i] * bb[j]) ** 2
        corner_norm = sum(c[2] * c[2] for c in corner)
        inner_part = (min(1.0, inner_w / 0.15)
                      if corner_norm > 1e-12 else 1.0)
        edge = []
        for k in (1, 2):
            if pi == 0:
                edge.append(((3 * pj + k) * nx + 3 * pi, ba[0] * bb[k]))
            if pi + 1 == cols:
                edge.append(((3 * pj + k) * nx + 3 * pi + 3,
                             ba[3] * bb[k]))
            if pj == 0:
                edge.append((3 * pj * nx + 3 * pi + k, ba[k] * bb[0]))
            if pj + 1 == rows:
                edge.append(((3 * pj + 3) * nx + 3 * pi + k,
                             ba[k] * bb[3]))
        edge_norm = sum(e[1] * e[1] for e in edge)
        edge_part = near_border if edge_norm > 1e-12 else 0.0
        inner_share = (1.0 - edge_part) * inner_part
        corner_share = (1.0 - edge_part) * (1.0 - inner_part)
        for _ in range(60):
            now = self.eval(s, t)
            rx = target[0] - now[0]
            ry = target[1] - now[1]
            if math.hypot(rx, ry) < 1e-9:
                break
            if inner_share > 0.0 and norm > 0.0:
                for j in (1, 2):
                    for i in (1, 2):
                        k = ba[i] * bb[j] / norm * inner_share
                        idx = (3 * pj + j) * nx + 3 * pi + i
                        p = self.points[idx]
                        self.points[idx] = (p[0] + rx * k, p[1] + ry * k)
            if edge_part > 0.0:
                for idx, w in edge:
                    k = w / edge_norm * edge_part
                    p = self.points[idx]
                    self.points[idx] = (p[0] + rx * k, p[1] + ry * k)
            if corner_share > 0.0 and corner_norm > 0.0:
                for ai, aj, w in corner:
                    k = w / corner_norm * corner_share
                    for dj in (-1, 0, 1):
                        for di in (-1, 0, 1):
                            i = 3 * ai + di
                            j = 3 * aj + dj
                            if 0 <= i < nx and 0 <= j < ny:
                                idx = j * nx + i
                                p = self.points[idx]
                                self.points[idx] = (p[0] + rx * k,
                                                    p[1] + ry * k)
            for _s in range(3):
                self._smooth_lines(max(0, 3 * pi - 3), 3 * pi + 7,
                                   max(0, 3 * pj - 3), 3 * pj + 7)

    def drag_point(self, base, index, d):
        """Drag one control point, carrying its handles."""
        if (len(base) != len(self.points) or index < 0
                or index >= len(base)
                or not (finite(d[0]) and finite(d[1]))):
            return
        self.points = list(base)
        nx = self.nx()
        ny = self.ny()
        i = index % nx
        j = index // nx

        def shift(ii, jj, dd):
            if 0 <= ii < nx and 0 <= jj < ny:
                p = self.points[jj * nx + ii]
                self.points[jj * nx + ii] = (p[0] + dd[0], p[1] + dd[1])

        def span(knots, k):
            if 0 < k < len(knots) - 1:
                return (knots[k] - knots[k - 1], knots[k + 1] - knots[k])
            return None
        ri = i % 3
        rj = j % 3
        if ri == 0 and rj == 0:
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    shift(i + di, j + dj, d)
        elif ri == 0:
            for di in (-1, 0, 1):
                shift(i + di, j, d)
            sp = span(self.vs, j // 3 + (1 if rj == 2 else 0))
            if sp is not None:
                hl, hr = sp
                if rj == 1:
                    other, k = j - 2, hl / hr
                else:
                    other, k = j + 2, hr / hl
                for di in (-1, 0, 1):
                    shift(i + di, other, (-d[0] * k, -d[1] * k))
        elif rj == 0:
            for dj in (-1, 0, 1):
                shift(i, j + dj, d)
            sp = span(self.us, i // 3 + (1 if ri == 2 else 0))
            if sp is not None:
                hl, hr = sp
                if ri == 1:
                    other, k = i - 2, hl / hr
                else:
                    other, k = i + 2, hr / hl
                for dj in (-1, 0, 1):
                    shift(other, j + dj, (-d[0] * k, -d[1] * k))
        else:
            shift(i, j, d)

    def bounds(self, steps=16):
        """Approximate document bounds of the warped surface."""
        nx = self.nx()
        ny = self.ny()
        min_x = min_y = 1e300
        max_x = max_y = -1e300
        for p in self.points:
            if not (finite(p[0]) and finite(p[1])):
                continue
            min_x = min(min_x, p[0])
            min_y = min(min_y, p[1])
            max_x = max(max_x, p[0])
            max_y = max(max_y, p[1])
        for j in range(steps + 1):
            for i in range(steps + 1):
                p = self.eval(i / float(steps), j / float(steps))
                if not (finite(p[0]) and finite(p[1])):
                    continue
                min_x = min(min_x, p[0])
                min_y = min(min_y, p[1])
                max_x = max(max_x, p[0])
                max_y = max(max_y, p[1])
        if max_x < min_x or max_y < min_y:
            return (0.0, 0.0, 1.0, 1.0)
        return (min_x, min_y, max_x - min_x, max_y - min_y)
