"""Turn a :class:`~flowblow.layout.Layout` into a standalone HTML document.

Design choices that make it look hand-drawn yet stay crisp:

* Node *shapes* and *edges* are SVG and pass through a turbulence-displacement
  filter (``#rough``) so every outline wobbles like a pen stroke.
* Node and edge *text* lives in an HTML overlay positioned on top of the SVG,
  so the Caveat font + MathJax LaTeX stay perfectly legible (they are not
  distorted by the rough filter).
"""
from __future__ import annotations

import html
import math
from typing import Dict, List, Tuple

from .assets import font_head
from .layout import Layout, PlacedNode
from .models import Diagram, Direction, EdgeStyle, Shape
from .templates import HTML_TEMPLATE

MATHJAX_CDN = r"""<script>
window.MathJax = {
  tex: { inlineMath: [['$', '$'], ['\\(', '\\)']],
         displayMath: [['$$', '$$'], ['\\[', '\\]']] },
  chtml: { scale: 1.25, matchFontHeight: false },
  startup: { typeset: true }
};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>"""


def _mathjax_head(mode: str) -> str:
    return MATHJAX_CDN if mode == "cdn" else "<!-- LaTeX rendering disabled -->"


# Centres the whole diagram in the viewport and scales it to fill a 16:9 (or
# any) frame.  Re-run after MathJax typesets so sizes are final.
_FIT_SCRIPT = """<script>
window.__fbFit = function () {
  var f = document.getElementById('fb-frame');
  if (!f) return;
  f.style.transform = 'none';
  var w = f.offsetWidth, h = f.offsetHeight;
  if (!w || !h) return;
  var vw = window.innerWidth, vh = window.innerHeight;
  var pad = Math.round(Math.min(vw, vh) * 0.045);
  var s = Math.min((vw - 2 * pad) / w, (vh - 2 * pad) / h);
  f.style.transform = 'translate(-50%,-50%) scale(' + s + ')';
};
document.addEventListener('DOMContentLoaded', window.__fbFit);
window.addEventListener('load', window.__fbFit);
</script>"""


def _mode_css(transparent: bool, fit: bool) -> str:
    css = []
    if transparent:
        # Drop the paper fill + dotted grid so the PNG has a clear background.
        css.append("body{background-color:transparent;background-image:none;}")
        # Labels need a little backing to stay readable over any background.
        css.append(".edge-label{background:rgba(255,255,255,0.82);box-shadow:none;}")
        css.append(".group-label{background:rgba(255,255,255,0.78);}")
    if fit:
        css.append("html,body{height:100%;width:100%;}")
        css.append("body{overflow:hidden;padding:0;}")
        css.append("#fb-frame{position:absolute;left:50%;top:50%;"
                   "transform-origin:center center;will-change:transform;}")
    return "\n".join(css)

# Pastel "highlighter" palette for node fills.
PALETTE = [
    "#ffd6a5", "#fdffb6", "#caffbf", "#9bf6ff",
    "#a0c4ff", "#bdb2ff", "#ffc6ff", "#ffadad",
    "#b9fbc0", "#fde4cf", "#cfbaf0", "#a3c4f3",
]


def _hash(s: str) -> int:
    h = 2166136261
    for ch in s:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h


def _jitter_angle(node_id: str) -> float:
    """Deterministic small rotation (degrees) so nodes look hand-placed."""
    return ((_hash(node_id) % 1000) / 1000.0 - 0.5) * 2.4  # ~ +/-1.2 deg


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _border_point(n: PlacedNode, toward: Tuple[float, float], inset: float) -> Tuple[float, float]:
    cx, cy = n.x, n.y
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = n.w / 2 * inset, n.h / 2 * inset
    sx = hw / abs(dx) if dx else math.inf
    sy = hh / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def _smooth_path(pts: List[Tuple[float, float]]) -> str:
    if len(pts) < 2:
        return ""
    if len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        return f"M {x0:.1f} {y0:.1f} L {x1:.1f} {y1:.1f}"
    p = [pts[0]] + pts + [pts[-1]]
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        d += f" C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def _arc_midpoint(pts: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(pts) == 1:
        return pts[0]
    total = 0.0
    seg = []
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        seg.append(d)
        total += d
    half = total / 2
    run = 0.0
    for (a, b), d in zip(zip(pts, pts[1:]), seg):
        if run + d >= half and d > 0:
            t = (half - run) / d
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        run += d
    return pts[len(pts) // 2]


def _arrow_head(tip: Tuple[float, float], from_pt: Tuple[float, float], size: float = 13.0) -> str:
    dx, dy = tip[0] - from_pt[0], tip[1] - from_pt[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    half = size * 0.55
    l = (bx + px * half, by + py * half)
    r = (bx - px * half, by - py * half)
    return (f'<path class="arrow" d="M {tip[0]:.1f} {tip[1]:.1f} '
            f'L {l[0]:.1f} {l[1]:.1f} L {r[0]:.1f} {r[1]:.1f} Z"/>')


# ---------------------------------------------------------------------------
# Shape generators -> SVG path/element strings (centred at cx,cy)
# ---------------------------------------------------------------------------
def _shape_svg(shape: Shape, cx: float, cy: float, w: float, h: float, fill: str, cls: str) -> str:
    hw, hh = w / 2, h / 2
    x0, y0, x1, y1 = cx - hw, cy - hh, cx + hw, cy + hh
    common = f'class="node-shape {cls}" fill="{fill}"'

    if shape in (Shape.rect,):
        return f'<rect {common} x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}"/>'
    if shape in (Shape.rounded,):
        r = min(w, h) * 0.18
        return f'<rect {common} x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}"/>'
    if shape in (Shape.stadium,):
        r = hh
        return f'<rect {common} x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}"/>'
    if shape in (Shape.ellipse,):
        return f'<ellipse {common} cx="{cx:.1f}" cy="{cy:.1f}" rx="{hw:.1f}" ry="{hh:.1f}"/>'
    if shape in (Shape.circle,):
        r = max(hw, hh)
        return f'<circle {common} cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>'
    if shape in (Shape.diamond,):
        pts = f"{cx:.1f},{y0:.1f} {x1:.1f},{cy:.1f} {cx:.1f},{y1:.1f} {x0:.1f},{cy:.1f}"
        return f'<polygon {common} points="{pts}"/>'
    if shape in (Shape.hexagon,):
        k = w * 0.2
        pts = (f"{x0 + k:.1f},{y0:.1f} {x1 - k:.1f},{y0:.1f} {x1:.1f},{cy:.1f} "
               f"{x1 - k:.1f},{y1:.1f} {x0 + k:.1f},{y1:.1f} {x0:.1f},{cy:.1f}")
        return f'<polygon {common} points="{pts}"/>'
    if shape in (Shape.parallelogram,):
        k = w * 0.18
        pts = f"{x0 + k:.1f},{y0:.1f} {x1:.1f},{y0:.1f} {x1 - k:.1f},{y1:.1f} {x0:.1f},{y1:.1f}"
        return f'<polygon {common} points="{pts}"/>'
    if shape in (Shape.cylinder,):
        ry = h * 0.12
        d = (f"M {x0:.1f},{y0 + ry:.1f} "
             f"A {hw:.1f},{ry:.1f} 0 0 0 {x1:.1f},{y0 + ry:.1f} "
             f"L {x1:.1f},{y1 - ry:.1f} "
             f"A {hw:.1f},{ry:.1f} 0 0 1 {x0:.1f},{y1 - ry:.1f} Z")
        top = (f'<path class="node-shape {cls}" fill="none" '
               f'd="M {x0:.1f},{y0 + ry:.1f} A {hw:.1f},{ry:.1f} 0 0 0 {x1:.1f},{y0 + ry:.1f}"/>')
        return f'<path {common} d="{d}"/>{top}'
    if shape in (Shape.cloud,):
        # A bumpy cloud made of arcs.
        d = (
            f"M {x0 + w*0.20:.1f},{y1 - h*0.18:.1f} "
            f"a {w*0.14:.1f},{h*0.16:.1f} 0 0 1 {-w*0.04:.1f},{-h*0.36:.1f} "
            f"a {w*0.16:.1f},{h*0.20:.1f} 0 0 1 {w*0.22:.1f},{-h*0.16:.1f} "
            f"a {w*0.18:.1f},{h*0.22:.1f} 0 0 1 {w*0.34:.1f},{h*0.02:.1f} "
            f"a {w*0.16:.1f},{h*0.18:.1f} 0 0 1 {w*0.16:.1f},{h*0.30:.1f} "
            f"a {w*0.14:.1f},{h*0.16:.1f} 0 0 1 {-w*0.10:.1f},{h*0.30:.1f} "
            f"a {w*0.20:.1f},{h*0.16:.1f} 0 0 1 {-w*0.30:.1f},{h*0.02:.1f} "
            f"a {w*0.16:.1f},{h*0.16:.1f} 0 0 1 {-w*0.24:.1f},{-h*0.16:.1f} Z"
        )
        return f'<path {common} d="{d}"/>'
    if shape in (Shape.note,):
        k = min(w, h) * 0.22
        d = (f"M {x0:.1f},{y0:.1f} L {x1 - k:.1f},{y0:.1f} L {x1:.1f},{y0 + k:.1f} "
             f"L {x1:.1f},{y1:.1f} L {x0:.1f},{y1:.1f} Z")
        fold = (f'<path class="node-shape {cls}" fill="none" '
                f'd="M {x1 - k:.1f},{y0:.1f} L {x1 - k:.1f},{y0 + k:.1f} L {x1:.1f},{y0 + k:.1f}"/>')
        return f'<path {common} d="{d}"/>{fold}'
    # fallback
    return f'<rect {common} x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8"/>'


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def render(diagram: Diagram, layout: Layout, fit: bool = False) -> str:
    node_meta = {n.id: n for n in diagram.nodes}
    group_color = {g.id: g.color for g in diagram.groups}

    svg_parts: List[str] = []
    overlay_parts: List[str] = []

    # --- groups (drawn first, behind everything) ---
    for i, g in enumerate(layout.groups):
        meta = next((x for x in diagram.groups if x.id == g.id), None)
        col = (meta.color if meta and meta.color else PALETTE[_hash(g.id) % len(PALETTE)])
        svg_parts.append(
            f'<rect class="group-box" x="{g.x:.1f}" y="{g.y:.1f}" width="{g.w:.1f}" '
            f'height="{g.h:.1f}" rx="16" style="--gcol:{col}"/>'
        )
        label = html.escape(meta.label if meta else g.id)
        overlay_parts.append(
            f'<div class="group-label" style="left:{g.x + 14:.1f}px;top:{g.y + 6:.1f}px;">{label}</div>'
        )

    # --- edges (behind nodes) ---
    round_shapes = (Shape.ellipse, Shape.circle, Shape.diamond)
    for e_spec, e in zip(_aligned_edges(diagram, layout), layout.edges):
        src = layout.nodes.get(e.source)
        tgt = layout.nodes.get(e.target)
        if not src or not tgt:
            continue
        pts = list(e.points)
        s_meta, t_meta = node_meta.get(e.source), node_meta.get(e.target)
        inset_s = 0.94 if (s_meta and s_meta.shape in round_shapes) else 1.0
        inset_t = 0.94 if (t_meta and t_meta.shape in round_shapes) else 1.0
        pts[0] = _border_point(src, pts[1], inset_s)
        pts[-1] = _border_point(tgt, pts[-2], inset_t)

        style = e_spec.style
        color = e_spec.color or "var(--ink)"
        dash = {EdgeStyle.solid: "", EdgeStyle.dashed: 'stroke-dasharray="9 7"',
                EdgeStyle.dotted: 'stroke-dasharray="2 7"'}[style]
        path = _smooth_path(pts)
        svg_parts.append(f'<path class="edge" d="{path}" {dash} style="stroke:{color}"/>')
        if e_spec.arrow:
            svg_parts.append(f'<g class="arrowg" style="fill:{color};stroke:{color}">'
                             f'{_arrow_head(pts[-1], pts[-2])}</g>')
        if e_spec.bidirectional:
            svg_parts.append(f'<g class="arrowg" style="fill:{color};stroke:{color}">'
                             f'{_arrow_head(pts[0], pts[1])}</g>')
        if e_spec.label:
            mx, my = _arc_midpoint(pts)
            overlay_parts.append(
                f'<div class="edge-label" style="left:{mx:.1f}px;top:{my:.1f}px;">'
                f'{html.escape(e_spec.label)}</div>'
            )

    # --- nodes ---
    for idx, (nid, pn) in enumerate(layout.nodes.items()):
        meta = node_meta.get(nid)
        shape = meta.shape if meta else Shape.rounded
        if meta and meta.color:
            fill = meta.color
        elif meta and meta.group and group_color.get(meta.group):
            fill = group_color[meta.group]
        else:
            fill = PALETTE[_hash(nid) % len(PALETTE)]
        angle = _jitter_angle(nid)

        shape_svg = _shape_svg(shape, pn.x, pn.y, pn.w, pn.h, fill, "rough")
        svg_parts.append(
            f'<g transform="rotate({angle:.2f} {pn.x:.1f} {pn.y:.1f})">{shape_svg}</g>'
        )

        icon_html = (f'<div class="node-icon">{html.escape(meta.icon)}</div>'
                     if meta and meta.icon else "")
        label_html = html.escape(meta.label) if meta else nid
        lw = pn.w - diagram.font_size * 0.9
        overlay_parts.append(
            f'<div class="node-label" style="left:{pn.x:.1f}px;top:{pn.y:.1f}px;'
            f'width:{lw:.1f}px;transform:translate(-50%,-50%) rotate({angle:.2f}deg);">'
            f'{icon_html}<div class="node-text">{label_html}</div></div>'
        )

    heading_block = (
        f'<div class="doc-title">{html.escape(diagram.title)}</div>'
        if diagram.title else ""
    )
    return HTML_TEMPLATE.format(
        title=html.escape(diagram.title or "FlowBlow diagram"),
        width=f"{layout.width:.0f}",
        height=f"{layout.height:.0f}",
        font_size=diagram.font_size,
        ink=diagram.accent,
        paper=diagram.paper,
        svg_body="\n".join(svg_parts),
        overlay_body="\n".join(overlay_parts),
        heading_block=heading_block,
        font_head=font_head(diagram.font_mode),
        mathjax_head=_mathjax_head(diagram.mathjax_mode),
        sketch_class="sketch" if diagram.sketch else "no-sketch",
        mode_css=_mode_css(diagram.transparent, fit),
        fit_script=_FIT_SCRIPT if fit else "",
    )


def _aligned_edges(diagram: Diagram, layout: Layout):
    """The original Edge specs in the same order layout produced placed edges.

    ``layout_diagram`` keeps only edges whose endpoints both exist, in input
    order, so we mirror that filtering to stay aligned with ``layout.edges``.
    """
    ids = set(layout.nodes)
    return [e for e in diagram.edges if e.source in ids and e.target in ids]
