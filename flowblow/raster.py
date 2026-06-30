"""Pure-Python (Pillow) renderer: draw a FlowBlow diagram straight to a PNG.

No browser, no HTML.  Shapes, edges and arrows are drawn with a hand-drawn
"rough" wobble (jittered, double-stroked paths), text uses the Caveat font,
and LaTeX is rasterised by :mod:`flowblow.mathtex` and composited in.  The
whole diagram is scaled to fill a 16:9 (or any) frame, on a transparent
background by default.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .content import Block, get_font, layout_block, render_emoji
from .layout import PlacedNode, layout_clustered, layout_diagram
from .mathtex import render_math
from .models import Diagram, Direction, EdgeStyle, Shape

# ---- palette (shared look with the HTML renderer) -------------------------
PALETTE = [
    "#ffd6a5", "#fdffb6", "#caffbf", "#9bf6ff",
    "#a0c4ff", "#bdb2ff", "#ffc6ff", "#ffadad",
    "#b9fbc0", "#fde4cf", "#cfbaf0", "#a3c4f3",
]

Point = Tuple[float, float]


def _hash(s: str) -> int:
    h = 2166136261
    for ch in s:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h


def _darken(col: str, factor: float) -> str:
    """Return ``col`` scaled toward black by ``factor`` (0..1), as #rrggbb."""
    r, g, b, _ = hex_rgba(col)
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def hex_rgba(col: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    col = (col or "#cccccc").strip()
    if not col.startswith("#"):
        return (200, 200, 200, alpha)
    h = col.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (200, 200, 200, alpha)
    return (r, g, b, alpha)


# ---------------------------------------------------------------------------
# Content measurement (drives node sizing in the layout engine)
# ---------------------------------------------------------------------------
def _node_block(node, font_size: float) -> Block:
    maxw = font_size * 11.0
    blk = layout_block(node.label, size=font_size, weight=600,
                       max_width=maxw, icon=node.icon)
    blk.size = font_size
    return blk


def _inflate(bw: float, bh: float, shape: Shape, fs: float) -> Tuple[float, float]:
    pad_x, pad_y = fs * 0.95, fs * 0.6
    w, h = bw + 2 * pad_x, bh + 2 * pad_y
    if shape == Shape.diamond:
        w, h = w * 1.5, h * 1.5
    elif shape == Shape.circle:
        side = max(w, h) * 1.18
        w = h = side
    elif shape == Shape.ellipse:
        w, h = w * 1.32, h * 1.25
    elif shape == Shape.hexagon:
        w *= 1.3
    elif shape == Shape.parallelogram:
        w *= 1.26
    elif shape == Shape.cylinder:
        h += fs * 0.9
    elif shape == Shape.cloud:
        w, h = w * 1.5, h * 1.5
    elif shape == Shape.note:
        w += fs * 0.4
    return max(w, fs * 3.2), max(h, fs * 2.2)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _border_point(n: PlacedNode, toward: Point, inset: float) -> Point:
    cx, cy = n.x, n.y
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = n.w / 2 * inset, n.h / 2 * inset
    s = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
    return cx + dx * s, cy + dy * s


def _catmull(points: Sequence[Point], samples: int = 16) -> List[Point]:
    """Sample a smooth Catmull-Rom spline through ``points``."""
    if len(points) <= 2:
        return list(points)
    p = [points[0]] + list(points) + [points[-1]]
    out: List[Point] = [points[0]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for s in range(1, samples + 1):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def _mid_and_tangent(pts):
    """Point at half the polyline's arc length, plus the local direction there.

    Robust for straight 2-point edges (returns the true geometric middle) and
    for curved multi-point edges alike.
    """
    if len(pts) < 2:
        return pts[0], (1.0, 0.0)
    segs, total = [], 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append(d)
        total += d
    half = total / 2
    run = 0.0
    for (a, b), d in zip(zip(pts, pts[1:]), segs):
        if run + d >= half and d > 0:
            t = (half - run) / d
            return ((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t),
                    (b[0] - a[0], b[1] - a[1]))
        run += d
    return pts[len(pts) // 2], (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])


def _dash(points: Sequence[Point], on: float, off: float) -> List[List[Point]]:
    """Split a polyline into dash sub-polylines by arc length."""
    if on <= 0:
        return [list(points)]
    segs: List[List[Point]] = []
    cur: List[Point] = []
    drawing = True
    remain = on
    prev = points[0]
    cur.append(prev)
    for pt in points[1:]:
        d = math.hypot(pt[0] - prev[0], pt[1] - prev[1])
        while d >= remain:
            t = remain / d if d else 0
            mid = (prev[0] + (pt[0] - prev[0]) * t, prev[1] + (pt[1] - prev[1]) * t)
            if drawing:
                cur.append(mid)
                segs.append(cur)
                cur = []
            else:
                cur = [mid]
            drawing = not drawing
            prev = mid
            d = math.hypot(pt[0] - prev[0], pt[1] - prev[1])
            remain = on if drawing else off
        remain -= d
        if drawing:
            cur.append(pt)
        prev = pt
    if drawing and len(cur) > 1:
        segs.append(cur)
    return segs


# ---------------------------------------------------------------------------
# The drawer -- everything below works in OUTPUT pixels.
# ---------------------------------------------------------------------------
class _Drawer:
    def __init__(self, img: Image.Image, unit: float, ox: float, oy: float, ink: str):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.unit = unit            # layout units -> output px
        self.ox, self.oy = ox, oy   # output origin offset
        self.accent = ink           # ink colour as hex string
        self.ink = hex_rgba(ink)
        self.stroke = max(1.4, 2.4 * unit)
        self.amp = 1.5 * unit
        self.seg = 13 * unit
        self.rng = random.Random(0)

    # coordinate transform
    def T(self, x: float, y: float) -> Point:
        return (x * self.unit + self.ox, y * self.unit + self.oy)

    # --- rough path utilities (input already in output px) ---
    def _roughen(self, pts: Sequence[Point], closed: bool, seed: int,
                 amp: Optional[float] = None, seg: Optional[float] = None) -> List[Point]:
        amp = self.amp if amp is None else amp
        seg = self.seg if seg is None else seg
        rng = random.Random(seed)
        out: List[Point] = []
        pairs = list(zip(pts, list(pts[1:]) + ([pts[0]] if closed else [])))
        for idx, (a, b) in enumerate(pairs):
            dx, dy = b[0] - a[0], b[1] - a[1]
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d, dx / d
            k = max(1, int(d / seg))
            for i in range(k):
                t = i / k
                fix_end = (not closed) and idx == 0 and i == 0
                off = 0.0 if fix_end else rng.uniform(-amp, amp)
                out.append((a[0] + dx * t + nx * off, a[1] + dy * t + ny * off))
        if closed:
            out.append(out[0])
        else:
            out.append(pts[-1])
        return out

    def stroke_path(self, pts: Sequence[Point], color, width=None, closed=False,
                    seed=0, passes=2):
        w = width if width is not None else self.stroke
        for pi in range(passes):
            rp = self._roughen(pts, closed, seed + pi * 97)
            self.d.line(rp, fill=color, width=max(1, int(round(w))), joint="curve")
        # round the joins a touch
        r = w / 2
        for (x, y) in (pts[0], pts[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def fill_poly(self, pts: Sequence[Point], fill, seed=0):
        rp = self._roughen(pts, True, seed)
        self.d.polygon(rp, fill=fill)

    def shape(self, pts: Sequence[Point], fill, seed=0):
        self.fill_poly(pts, fill, seed)
        self.stroke_path(list(pts) + [pts[0]], self.ink, closed=False, seed=seed + 5, passes=2)

    # --- composite an image piece (math / emoji) scaled to target height ---
    def blit(self, piece: Image.Image, cx: float, cy: float, target_h: float):
        if piece is None or piece.height == 0:
            return
        tw = max(1, int(round(piece.width * target_h / piece.height)))
        th = max(1, int(round(target_h)))
        rs = piece.resize((tw, th), Image.LANCZOS)
        self.img.alpha_composite(rs, (int(round(cx - tw / 2)), int(round(cy - th / 2))))

    # --- draw a rich-text block centred at output (cx, cy) ---
    def text_block(self, blk: Block, cx: float, cy: float, weight: int, color: str):
        u = self.unit
        size_px = getattr(blk, "size", 24) * u
        font = get_font(weight, size_px)
        fill = hex_rgba(color)
        total_h = blk.h * u
        cur_y = cy - total_h / 2
        spacing = 1.06
        for ln in blk.lines:
            line_h = ln.h * u
            line_w = ln.w * u
            lx = cx - line_w / 2
            yc = cur_y + line_h / 2
            for r in ln.runs:
                rx = lx + r.x * u
                if r.kind == "text":
                    self.d.text((rx, yc), r.payload, font=font, fill=fill, anchor="lm")
                elif r.kind == "math":
                    self.blit(render_math(r.payload, color), rx + (r.w * u) / 2, yc, r.h * u)
                elif r.kind == "icon":
                    self.blit(render_emoji(r.payload), rx + (r.w * u) / 2, yc, r.h * u)
            cur_y += line_h * spacing

    def label_with_halo(self, blk: Block, cx: float, cy: float, weight: int,
                        color: str, halo=(255, 255, 255)):
        """Draw a label with a soft white knockout so it reads over any line
        (no boxy pill)."""
        u = self.unit
        pad = int(round(5 * u)) + 2
        w = max(1, int(math.ceil(blk.w * u)) + 2 * pad)
        h = max(1, int(math.ceil(blk.h * u)) + 2 * pad)
        tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sub = _Drawer(tile, u, 0, 0, self.accent)
        sub.text_block(blk, w / 2, h / 2, weight, color)
        # build a dilated, blurred white halo from the text's alpha
        r = max(1, int(round(2.4 * u)))
        alpha = tile.getchannel("A").filter(ImageFilter.MaxFilter(2 * r + 1))
        alpha = alpha.filter(ImageFilter.GaussianBlur(max(0.6, u * 0.7)))
        halo_img = Image.new("RGBA", tile.size, halo + (255,))
        halo_img.putalpha(alpha)
        composed = Image.alpha_composite(halo_img, tile)
        self.img.alpha_composite(composed, (int(round(cx - w / 2)), int(round(cy - h / 2))))


# ---------------------------------------------------------------------------
# Shape vertex generators (centre cx,cy ; size w,h ; OUTPUT px)
# ---------------------------------------------------------------------------
def _ellipse_pts(cx, cy, w, h, n=48):
    return [(cx + w / 2 * math.cos(2 * math.pi * i / n),
             cy + h / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rounded_pts(cx, cy, w, h, r, per=6):
    hw, hh = w / 2, h / 2
    r = min(r, hw, hh)
    cs = [(cx + hw - r, cy + hh - r, 0),
          (cx - hw + r, cy + hh - r, 90),
          (cx - hw + r, cy - hh + r, 180),
          (cx + hw - r, cy - hh + r, 270)]
    pts = []
    for ccx, ccy, a0 in cs:
        for i in range(per + 1):
            a = math.radians(a0 + 90 * i / per)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def _cloud_pts(cx, cy, w, h, n=60):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        bump = 1 + 0.13 * math.sin(6 * a) + 0.05 * math.sin(11 * a + 1.3)
        pts.append((cx + (w / 2) * 0.92 * bump * math.cos(a),
                    cy + (h / 2) * 0.92 * bump * math.sin(a)))
    return pts


def _shape_points(shape: Shape, cx, cy, w, h):
    hw, hh = w / 2, h / 2
    x0, y0, x1, y1 = cx - hw, cy - hh, cx + hw, cy + hh
    if shape == Shape.rect:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if shape == Shape.rounded or shape == Shape.note:
        return _rounded_pts(cx, cy, w, h, min(w, h) * 0.18)
    if shape == Shape.stadium:
        return _rounded_pts(cx, cy, w, h, hh)
    if shape == Shape.ellipse:
        return _ellipse_pts(cx, cy, w, h)
    if shape == Shape.circle:
        return _ellipse_pts(cx, cy, max(w, h), max(w, h))
    if shape == Shape.diamond:
        return [(cx, y0), (x1, cy), (cx, y1), (x0, cy)]
    if shape == Shape.hexagon:
        k = w * 0.2
        return [(x0 + k, y0), (x1 - k, y0), (x1, cy), (x1 - k, y1), (x0 + k, y1), (x0, cy)]
    if shape == Shape.parallelogram:
        k = w * 0.18
        return [(x0 + k, y0), (x1, y0), (x1 - k, y1), (x0, y1)]
    if shape == Shape.cloud:
        return _cloud_pts(cx, cy, w, h)
    return _rounded_pts(cx, cy, w, h, min(w, h) * 0.18)


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------
def _draw_scene(diagram: Diagram, layout, blocks, unit: float,
                ox: float, oy: float, img: Image.Image) -> None:
    dr = _Drawer(img, unit, ox, oy, diagram.accent)
    node_meta = {n.id: n for n in diagram.nodes}
    group_meta = {g.id: g for g in diagram.groups}
    group_color = {g.id: g.color for g in diagram.groups}
    obstacles: List[Tuple[float, float, float, float]] = []  # node + group-label rects

    # --- groups (behind) ---
    for g in layout.groups:
        meta = group_meta.get(g.id)
        col = (meta.color if meta and meta.color else PALETTE[_hash(g.id) % len(PALETTE)])
        x0, y0 = dr.T(g.x, g.y)
        x1, y1 = dr.T(g.x + g.w, g.y + g.h)
        pts = _rounded_pts((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, 16 * unit)
        dr.fill_poly(pts, hex_rgba(col, 28), seed=_hash(g.id) & 255)
        for piece in _dash([*pts, pts[0]], 5 * unit, 7 * unit):
            if len(piece) > 1:
                dr.d.line(piece, fill=hex_rgba(diagram.accent, 120),
                          width=max(1, int(round(dr.stroke * 0.8))), joint="curve")
        if meta and meta.label:
            gb = layout_block(meta.label, size=diagram.font_size * 1.0, weight=700)
            gb.size = diagram.font_size * 1.0
            # title in the group's highlight colour, sitting just ABOVE the box
            tint = _darken(col, 0.72)
            lx = x0 + gb.w * unit / 2 + 6 * unit
            ly = y0 - gb.h * unit / 2 - 5 * unit
            dr.label_with_halo(gb, lx, ly, 700, tint)
            obstacles.append((lx - gb.w * unit / 2, ly - gb.h * unit / 2,
                              lx + gb.w * unit / 2, ly + gb.h * unit / 2))

    # --- edges --- (labels are deferred so nodes never hide them)
    deferred_labels: list = []  # (block, mid, perp, color, weight)
    round_shapes = (Shape.ellipse, Shape.circle, Shape.diamond)
    valid = [e for e in diagram.edges
             if e.source in layout.nodes and e.target in layout.nodes]

    # Bow parallel / back edges apart so they each get their own arc instead of
    # overlapping on the same line.
    BOW = 30.0  # layout units
    pair_idx: dict = {}
    for k, e in enumerate(layout.edges):
        pair_idx.setdefault(frozenset((e.source, e.target)), []).append(k)
    bow_of: dict = {}
    for key, idxs in pair_idx.items():
        if len(idxs) > 1 and len(key) == 2:
            n = len(idxs)
            for j, k in enumerate(idxs):
                bow_of[k] = (j - (n - 1) / 2.0) * 2.0 * BOW

    def draw_arrow(tip: Point, frm: Point, color):
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        size = 13 * unit
        base = (tip[0] - ux * size, tip[1] - uy * size)
        half = size * 0.6
        dr.d.polygon([tip, (base[0] + px * half, base[1] + py * half),
                      (base[0] - px * half, base[1] - py * half)], fill=color)

    for k, (spec, e) in enumerate(zip(valid, layout.edges)):
        src, tgt = layout.nodes[e.source], layout.nodes[e.target]
        s_meta, t_meta = node_meta.get(e.source), node_meta.get(e.target)
        inset_s = 0.94 if (s_meta and s_meta.shape in round_shapes) else 1.0
        inset_t = 0.94 if (t_meta and t_meta.shape in round_shapes) else 1.0
        raw = list(e.points)
        bow = bow_of.get(k, 0.0)

        if bow and len(raw) == 2:
            (sx, sy), (ex, ey) = raw
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            ddx, ddy = ex - sx, ey - sy
            L = math.hypot(ddx, ddy) or 1.0
            ctrl = (mx - ddy / L * bow, my + ddx / L * bow)
            p0 = _border_point(src, ctrl, inset_s)
            p1 = _border_point(tgt, ctrl, inset_t)
            control = [p0, ctrl, p1]
        else:
            control = raw
            control[0] = _border_point(src, control[1], inset_s)
            control[-1] = _border_point(tgt, control[-2], inset_t)

        sampled = [dr.T(*p) for p in _catmull(control, samples=22)]
        color = hex_rgba(spec.color) if spec.color else dr.ink
        seed = _hash(e.source + e.target) & 255
        # jitter the whole curve ONCE, then dash that single wavy path so the
        # dashes stay connected and follow the curve.
        wavy = dr._roughen(sampled, closed=False, seed=seed,
                           amp=1.05 * unit, seg=11 * unit)
        wdt = max(1, int(round(dr.stroke)))

        if spec.style == EdgeStyle.dashed:
            pieces = _dash(wavy, 17 * unit, 11 * unit)
        elif spec.style == EdgeStyle.dotted:
            pieces = _dash(wavy, 3.5 * unit, 7 * unit)
        else:
            pieces = [wavy]
        for piece in pieces:
            if len(piece) > 1:
                dr.d.line(piece, fill=color, width=wdt, joint="curve")

        if spec.arrow:
            draw_arrow(sampled[-1], sampled[-2], color)
        if spec.bidirectional:
            draw_arrow(sampled[0], sampled[1], color)

        # edge label (deferred), anchored at the true arc-length MIDDLE of the
        # edge (not the midpoint index, which for a straight 2-point edge is the
        # endpoint by the arrowhead).
        if spec.label:
            mid, tangent = _mid_and_tangent(sampled)
            dx, dy = tangent
            L = math.hypot(dx, dy) or 1.0
            perp = (-dy / L, dx / L)
            if perp[1] > 0:                # prefer the "upper" side
                perp = (-perp[0], -perp[1])
            # yes/no decision labels -> a big green "Y" / red "N"
            low = spec.label.strip().lower()
            if low in ("yes", "y"):
                text, lcolor, lsize, weight = "Y", "#2e9e3f", diagram.font_size * 1.9, 700
            elif low in ("no", "n"):
                text, lcolor, lsize, weight = "N", "#d83a3a", diagram.font_size * 1.9, 700
            else:
                text, lcolor, lsize, weight = spec.label, diagram.accent, diagram.font_size, 600
            lb = layout_block(text, size=lsize, weight=weight,
                              max_width=diagram.font_size * 14)
            lb.size = lsize
            deferred_labels.append((lb, mid, perp, lcolor, weight))

    # --- nodes ---
    for nid, pn in layout.nodes.items():
        meta = node_meta.get(nid)
        shape = meta.shape if meta else Shape.rounded
        if meta and meta.color:
            fill = meta.color
        elif meta and meta.group and group_color.get(meta.group):
            fill = group_color[meta.group]
        else:
            fill = PALETTE[_hash(nid) % len(PALETTE)]
        cx, cy = dr.T(pn.x, pn.y)
        w, h = pn.w * unit, pn.h * unit
        obstacles.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        seed = _hash(nid) & 255
        fill_rgba = hex_rgba(fill, 235)

        if shape == Shape.cylinder:
            _draw_cylinder(dr, cx, cy, w, h, fill_rgba, seed)
        else:
            dr.shape(_shape_points(shape, cx, cy, w, h), fill_rgba, seed=seed)
            if shape == Shape.note:
                _draw_note_fold(dr, cx, cy, w, h)

        blk = blocks[nid]
        dr.text_block(blk, cx, cy, 600, diagram.accent)

    # --- edge labels on top (soft halo, no boxy pill) ---
    def _clearance(cx, cy, hw, hh):
        """Signed distance from the label rect to the NEAREST obstacle.
        Positive = that much empty space around it; negative = overlapping."""
        best = 1e18
        for (x0, y0, x1, y1) in obstacles:
            dx = max(x0 - (cx + hw), (cx - hw) - x1, 0.0)
            dy = max(y0 - (cy + hh), (cy - hh) - y1, 0.0)
            if dx > 0 or dy > 0:
                dist = math.hypot(dx, dy)
            else:  # overlapping -> negative penetration depth
                dist = -min((cx + hw) - x0, x1 - (cx - hw),
                            (cy + hh) - y0, y1 - (cy - hh))
            best = min(best, dist)
        return best

    for lb, mid, perp, lcolor, lweight in deferred_labels:
        hw, hh = lb.w * unit / 2, lb.h * unit / 2
        # Keep the label at the MIDDLE of the line, beside it. On each side,
        # step out from the line just far enough to clear any node; then prefer
        # the side that clears with the least travel (i.e. the open side).
        base = hh + 6 * unit
        step = hh * 0.8
        margin = 2 * unit
        cands = []  # (cleared?, offset_used, score, pos)
        for sign in (1, -1):
            o = base
            chosen = (mid[0] + perp[0] * sign * o, mid[1] + perp[1] * sign * o)
            sc_best = _clearance(*chosen, hw, hh)
            cleared, off_used = sc_best >= margin, o
            for _ in range(6):
                cx = mid[0] + perp[0] * sign * o
                cy = mid[1] + perp[1] * sign * o
                sc = _clearance(cx, cy, hw, hh)
                if sc >= margin:
                    chosen, off_used, cleared = (cx, cy), o, True
                    break
                if sc > sc_best:
                    sc_best, chosen, off_used = sc, (cx, cy), o
                o += step
            cands.append((cleared, off_used, sc_best, chosen))
        clears = [c for c in cands if c[0]]
        best = (min(clears, key=lambda c: c[1])[3] if clears
                else max(cands, key=lambda c: c[2])[3])
        # keep the label fully inside the canvas so it never clips at the edge
        W, H = dr.img.size
        bx = min(max(best[0], hw + 4), W - hw - 4)
        by = min(max(best[1], hh + 4), H - hh - 4)
        dr.label_with_halo(lb, bx, by, lweight, lcolor)


def _draw_cylinder(dr: _Drawer, cx, cy, w, h, fill, seed):
    ry = h * 0.12
    x0, x1 = cx - w / 2, cx + w / 2
    y0, y1 = cy - h / 2, cy + h / 2
    body = [(x0, y0 + ry)] + _ellipse_pts(cx, y1 - ry, w, 2 * ry)[0:25] + [(x1, y0 + ry)]
    dr.d.rectangle([x0, y0 + ry, x1, y1 - ry], fill=fill)
    dr.d.ellipse([x0, y1 - 2 * ry, x1, y1], fill=fill)
    dr.d.ellipse([x0, y0, x1, y0 + 2 * ry], fill=fill)
    # outline
    dr.stroke_path([(x0, y0 + ry), (x0, y1 - ry)], dr.ink, passes=2, seed=seed)
    dr.stroke_path([(x1, y0 + ry), (x1, y1 - ry)], dr.ink, passes=2, seed=seed + 1)
    dr.stroke_path(_ellipse_pts(cx, y0 + ry, w, 2 * ry), dr.ink, closed=True, passes=2, seed=seed + 2)
    front = _ellipse_pts(cx, y1 - ry, w, 2 * ry)
    front = [p for p in front if p[1] >= y1 - ry - 0.5]
    dr.stroke_path(front, dr.ink, passes=2, seed=seed + 3)


def _draw_note_fold(dr: _Drawer, cx, cy, w, h):
    k = min(w, h) * 0.22
    x1, y0 = cx + w / 2, cy - h / 2
    dr.stroke_path([(x1 - k, y0), (x1 - k, y0 + k), (x1, y0 + k)], dr.ink, passes=1)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
_ROTATE = {Direction.TB: Direction.LR, Direction.LR: Direction.TB,
           Direction.BT: Direction.RL, Direction.RL: Direction.BT}


def _stretch_vertical(layout, factor: float, top: float = 0.0) -> None:
    """Spread everything out along Y by ``factor`` (node sizes unchanged) so a
    short diagram fills the vertical length of a tall frame."""
    def sy(y):
        return top + (y - top) * factor
    for pn in layout.nodes.values():
        pn.y = sy(pn.y)
    for e in layout.edges:
        e.points = [(x, sy(y)) for (x, y) in e.points]
    for g in layout.groups:
        y0, y1 = sy(g.y), sy(g.y + g.h)
        g.y, g.h = y0, y1 - y0
    layout.height = sy(layout.height)


def _scene_size(layout, title_block, fs):
    top = (title_block.h + fs * 1.1) if title_block else 0.0
    scene_w = max(layout.width, title_block.w if title_block else 0)
    scene_h = layout.height + top
    return scene_w, scene_h, top


def render_png_bytes(diagram: Diagram, width: int = 1080, height: int = 1920,
                     scale: float = 2.0, transparent: bool = True,
                     pad_frac: float = 0.035, supersample: int = 2,
                     auto_orient: bool = True) -> bytes:
    import io

    fs = diagram.font_size
    blocks = {n.id: _node_block(n, fs) for n in diagram.nodes}

    def measure(node, font_size):
        b = blocks[node.id]
        return _inflate(b.w, b.h, node.shape, font_size)

    title_block = None  # titles are not drawn

    fw, fh = int(width * scale), int(height * scale)
    pad = pad_frac * min(fw, fh)

    # Try the requested orientation and its 90-degree rotation, then keep
    # whichever fills the frame best -- so a tall flow is laid out sideways to
    # make the most of a wide 16:9 canvas.
    candidates = [diagram.direction]
    if auto_orient and _ROTATE[diagram.direction] not in candidates:
        candidates.append(_ROTATE[diagram.direction])

    best = None
    for direction in candidates:
        diagram.direction = direction
        cand_layout = layout_clustered(diagram, measure=measure)
        sw, sh, top = _scene_size(cand_layout, title_block, fs)
        cand_fit = min((fw - 2 * pad) / sw, (fh - 2 * pad) / sh)
        if best is None or cand_fit > best[0] + 1e-9:
            best = (cand_fit, direction, cand_layout, sw, sh, top)

    fit, chosen, layout, scene_w, scene_h, top = best
    diagram.direction = chosen

    # extra margin so bowed arcs / floated labels never clip at the edge
    B = fs * 1.9

    # Use the full vertical length: if the frame is taller than the diagram
    # needs (width is the binding dimension), spread the rows vertically to
    # fill the height instead of leaving slack.
    fit_w = (fw - 2 * pad) / (scene_w + 2 * B)
    fit_h = (fh - 2 * pad) / (scene_h + 2 * B)
    if fit_h > fit_w * 1.02:
        target_h = (fh - 2 * pad) / fit_w - 2 * B
        factor = min(target_h / scene_h, 2.4)
        if factor > 1.0:
            _stretch_vertical(layout, factor)
            scene_w, scene_h, top = _scene_size(layout, title_block, fs)

    diagram_ox = (scene_w - layout.width) / 2
    total_w, total_h = scene_w + 2 * B, scene_h + 2 * B
    fit = min((fw - 2 * pad) / total_w, (fh - 2 * pad) / total_h)

    ss = max(1, supersample)
    unit = fit * ss
    scene_px_w = int(math.ceil(total_w * unit)) + 2
    scene_px_h = int(math.ceil(total_h * unit)) + 2

    scene = Image.new("RGBA", (scene_px_w, scene_px_h), (0, 0, 0, 0))
    _draw_scene(diagram, layout, blocks, unit,
                ox=(B + diagram_ox) * unit, oy=(B + top) * unit, img=scene)

    # title
    if title_block is not None:
        tdr = _Drawer(scene, unit, 0, 0, diagram.accent)
        tcx = (B + scene_w / 2) * unit
        tdr.text_block(title_block, tcx, (B + title_block.h / 2 + fs * 0.2) * unit,
                       700, diagram.accent)
        # little underline flourish
        uw = title_block.w * unit * 0.6
        uy = (B + title_block.h + fs * 0.25) * unit
        tdr.stroke_path([(tcx - uw / 2, uy), (tcx + uw / 2, uy)],
                        hex_rgba(diagram.accent, 140), width=max(1, 2 * unit), passes=1)

    # downsample supersample
    if ss > 1:
        scene = scene.resize((max(1, scene_px_w // ss), max(1, scene_px_h // ss)),
                             Image.LANCZOS)

    # compose onto the frame
    bg = (0, 0, 0, 0) if transparent else hex_rgba(diagram.paper)
    frame = Image.new("RGBA", (fw, fh), bg)
    px = (fw - scene.width) // 2
    py = (fh - scene.height) // 2
    frame.alpha_composite(scene, (px, py))

    buf = io.BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()
