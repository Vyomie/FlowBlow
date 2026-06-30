"""A self-contained layered ("Sugiyama") graph layout engine.

No third-party dependencies -- it implements the classic pipeline:

1. break cycles so we can treat the graph as a DAG,
2. assign every node to a layer (longest-path ranking),
3. insert virtual "dummy" nodes so long edges route cleanly between layers,
4. order nodes within each layer to reduce edge crossings (median heuristic),
5. assign cross-axis coordinates (priority / averaging method),
6. project the abstract (rank, cross) coordinates into pixel x/y depending on
   the requested flow direction.

The output is consumed by ``render.py``.  Everything is measured in pixels.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import Diagram, Direction, Edge, Node, Shape

# ---------------------------------------------------------------------------
# Tunable spacing constants (pixels)
# ---------------------------------------------------------------------------
LAYER_GAP = 60          # spacing between successive layers (along main axis)
SIBLING_GAP = 44        # min spacing between nodes inside the same layer
GROUP_GAP = 64          # extra spacing between nodes of different groups
COMPONENT_GAP = 80      # spacing between disconnected components
DUMMY_SIZE = 2          # cross-extent of a virtual routing node
MARGIN = 24             # outer canvas margin (kept small; PNG fit adds framing)
GROUP_PAD = 26          # padding of a cluster box around its members


# ---------------------------------------------------------------------------
# Node-size estimation (we cannot measure the browser, so we approximate)
# ---------------------------------------------------------------------------
_TEX_RE = re.compile(r"\${1,2}.*?\${1,2}", re.S)


def _visible_len(text: str) -> int:
    """Rough printable length, treating a LaTeX span as a chunky token."""
    # Replace each math span with a fixed-ish width proportional to its content.
    def repl(m: re.Match) -> str:
        inner = m.group(0).strip("$")
        return "M" * max(3, len(inner) // 2)

    return len(_TEX_RE.sub(repl, text))


def _wrap(text: str, max_chars: int) -> List[str]:
    """Greedy word wrap that keeps ``$...$`` math spans intact."""
    if not text:
        return [""]
    # Protect math spans from being split on spaces.
    spans: List[str] = []

    def stash(m: re.Match) -> str:
        spans.append(m.group(0))
        return f"\0{len(spans) - 1}\0"

    protected = _TEX_RE.sub(stash, text)

    def restore(tok: str) -> str:
        return re.sub(r"\0(\d+)\0", lambda m: spans[int(m.group(1))], tok)

    lines: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for raw in protected.split():
        word = restore(raw)
        wlen = _visible_len(word)
        if cur and cur_len + 1 + wlen > max_chars:
            lines.append(" ".join(cur))
            cur, cur_len = [word], wlen
        else:
            cur.append(word)
            cur_len += (1 if cur_len else 0) + wlen
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def estimate_size(label: str, shape: Shape, font_size: int, has_icon: bool) -> Tuple[float, float, List[str]]:
    """Estimate a node's pixel ``(width, height, wrapped_lines)``.

    Caveat is a condensed handwriting face, so the average glyph advance is
    well below the font size.  These constants were tuned by eye.
    """
    char_w = font_size * 0.42
    line_h = font_size * 1.18
    max_chars = 24

    lines = _wrap(label, max_chars)
    text_w = max((_visible_len(l) for l in lines), default=1) * char_w
    text_h = len(lines) * line_h
    if has_icon:
        text_h += line_h  # room for the icon glyph above the text

    pad_x, pad_y = font_size * 0.95, font_size * 0.7
    w = text_w + 2 * pad_x
    h = text_h + 2 * pad_y

    # Shape-specific minimum proportions / inflation for the geometry.
    if shape in (Shape.diamond,):
        w *= 1.5
        h *= 1.5
    elif shape in (Shape.circle,):
        side = max(w, h)
        w = h = side * 1.15
    elif shape in (Shape.ellipse, Shape.hexagon, Shape.parallelogram):
        w *= 1.25
        h *= 1.1
    elif shape in (Shape.cloud,):
        w *= 1.4
        h *= 1.45
    elif shape in (Shape.cylinder,):
        h += font_size * 0.9

    w = max(w, font_size * 3.2)
    h = max(h, font_size * 2.2)
    return w, h, lines


# ---------------------------------------------------------------------------
# Internal layout structures
# ---------------------------------------------------------------------------
@dataclass
class LNode:
    id: str
    w: float = DUMMY_SIZE
    h: float = DUMMY_SIZE
    rank: int = 0
    order: int = 0
    cross: float = 0.0      # centre coordinate along the cross axis
    main: float = 0.0       # centre coordinate along the main axis
    dummy: bool = False
    lines: List[str] = field(default_factory=list)


@dataclass
class LEdge:
    u: str
    v: str
    reversed: bool = False
    chain: List[str] = field(default_factory=list)  # u, dummies..., v


@dataclass
class PlacedNode:
    id: str
    x: float
    y: float
    w: float
    h: float
    lines: List[str]


@dataclass
class PlacedEdge:
    source: str
    target: str
    points: List[Tuple[float, float]]   # poly-line through node centres
    reversed: bool


@dataclass
class PlacedGroup:
    id: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class Layout:
    width: float
    height: float
    nodes: Dict[str, PlacedNode]
    edges: List[PlacedEdge]
    groups: List[PlacedGroup]


class _Engine:
    def __init__(self, diagram: Diagram, measure=None):
        self.d = diagram
        # measure(node, font_size) -> (width, height); defaults to estimation.
        self.measure = measure
        self.nodes: Dict[str, LNode] = {}
        self.edges: List[LEdge] = []
        self.group_of: Dict[str, Optional[str]] = {}
        self.adj: Dict[str, List[str]] = {}
        self.radj: Dict[str, List[str]] = {}
        self.layers: List[List[str]] = []
        self._dummy_seq = 0
        self.horizontal = diagram.direction in (Direction.LR, Direction.RL)

    # -- build --------------------------------------------------------------
    def build(self) -> None:
        fs = self.d.font_size
        for n in self.d.nodes:
            if self.measure is not None:
                w, h = self.measure(n, fs)
                lines = []
            else:
                w, h, lines = estimate_size(n.label, n.shape, fs, bool(n.icon))
            self.nodes[n.id] = LNode(id=n.id, w=w, h=h, lines=lines)
            self.group_of[n.id] = n.group
            self.adj.setdefault(n.id, [])
            self.radj.setdefault(n.id, [])
        for e in self.d.edges:
            if e.source not in self.nodes or e.target not in self.nodes:
                continue
            self.edges.append(LEdge(u=e.source, v=e.target))

    # -- 1. cycle breaking --------------------------------------------------
    def break_cycles(self) -> None:
        state: Dict[str, int] = {nid: 0 for nid in self.nodes}  # 0=new 1=stack 2=done
        order = list(self.nodes)
        out: Dict[str, List[LEdge]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            out[e.u].append(e)

        def dfs(start: str) -> None:
            stack = [(start, iter(out[start]))]
            state[start] = 1
            while stack:
                node, it = stack[-1]
                advanced = False
                for e in it:
                    if state[e.v] == 1:        # back edge -> reverse it
                        e.reversed = True
                        e.u, e.v = e.v, e.u
                    elif state[e.v] == 0:
                        state[e.v] = 1
                        stack.append((e.v, iter(out[e.v])))
                        advanced = True
                        break
                if not advanced:
                    state[node] = 2
                    stack.pop()

        for nid in order:
            if state[nid] == 0:
                dfs(nid)

        # Rebuild adjacency from the (now acyclic) edge list.
        for nid in self.nodes:
            self.adj[nid] = []
            self.radj[nid] = []
        for e in self.edges:
            self.adj[e.u].append(e.v)
            self.radj[e.v].append(e.u)

    # -- 2. layering (longest path) ----------------------------------------
    def assign_ranks(self) -> None:
        rank: Dict[str, int] = {}

        def longest(nid: str) -> int:
            if nid in rank:
                return rank[nid]
            rank[nid] = 0  # guard
            preds = self.radj[nid]
            r = 0 if not preds else max(longest(p) for p in preds) + 1
            rank[nid] = r
            return r

        for nid in self.nodes:
            longest(nid)

        # Pull every node as close to its successors as possible (tighten).
        changed = True
        while changed:
            changed = False
            for nid in self.nodes:
                succ = self.adj[nid]
                if succ:
                    target = min(rank[s] for s in succ) - 1
                    if target > rank[nid]:
                        rank[nid] = target
                        changed = True

        for nid, r in rank.items():
            self.nodes[nid].rank = r

    # -- 3. dummy nodes for long edges -------------------------------------
    def add_dummies(self) -> None:
        for e in self.edges:
            r1, r2 = self.nodes[e.u].rank, self.nodes[e.v].rank
            if r2 - r1 <= 1:
                e.chain = [e.u, e.v]
                continue
            chain = [e.u]
            for r in range(r1 + 1, r2):
                did = f"__dummy_{self._dummy_seq}"
                self._dummy_seq += 1
                dn = LNode(id=did, dummy=True, rank=r)
                self.nodes[did] = dn
                self.adj.setdefault(did, [])
                self.radj.setdefault(did, [])
                chain.append(did)
            chain.append(e.v)
            e.chain = chain

    # -- 4. ordering within layers (median heuristic) ----------------------
    def order_layers(self) -> None:
        max_rank = max((n.rank for n in self.nodes.values()), default=0)
        self.layers = [[] for _ in range(max_rank + 1)]
        for nid, n in self.nodes.items():
            self.layers[n.rank].append(nid)

        # Adjacency that includes dummy chain links.
        up: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        down: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            for a, b in zip(e.chain, e.chain[1:]):
                down[a].append(b)
                up[b].append(a)

        # Initialise order by current insertion, then refine.
        for layer in self.layers:
            for i, nid in enumerate(layer):
                self.nodes[nid].order = i

        def median(nid: str, neigh: Dict[str, List[str]]) -> float:
            ns = neigh[nid]
            if not ns:
                return -1.0
            pos = sorted(self.nodes[x].order for x in ns)
            m = len(pos)
            mid = m // 2
            if m % 2 == 1:
                return float(pos[mid])
            if m == 2:
                return (pos[0] + pos[1]) / 2.0
            left = pos[mid - 1] - pos[0]
            right = pos[-1] - pos[mid]
            if left + right == 0:
                return (pos[mid - 1] + pos[mid]) / 2.0
            return (pos[mid - 1] * right + pos[mid] * left) / (left + right)

        def reorder(neigh: Dict[str, List[str]]) -> None:
            for layer in self.layers:
                meds = [(median(nid, neigh), i, nid) for i, nid in enumerate(layer)]
                # nodes with no neighbours (median -1) keep their slot
                fixed = [(i, nid) for (m, i, nid) in meds if m < 0]
                movable = sorted([t for t in meds if t[0] >= 0])
                result: List[Optional[str]] = [None] * len(layer)
                for i, nid in fixed:
                    result[i] = nid
                slots = [i for i in range(len(layer)) if result[i] is None]
                for slot, (_, _, nid) in zip(slots, movable):
                    result[slot] = nid
                layer[:] = [r for r in result if r is not None]
                for i, nid in enumerate(layer):
                    self.nodes[nid].order = i

        for it in range(6):
            reorder(up if it % 2 == 0 else down)

        # Keep each group's nodes contiguous within every layer so its highlight
        # box forms its own band and does not overlap other groups' boxes.
        self._group_contiguous_order()

    def _group_contiguous_order(self) -> None:
        if not any(self.group_of.get(n) for n in self.nodes):
            return
        # A representative cross position per group = mean of normalised orders.
        sums: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        for layer in self.layers:
            n = max(1, len(layer) - 1)
            for i, nid in enumerate(layer):
                g = self.group_of.get(nid)
                if g:
                    sums[g] = sums.get(g, 0.0) + i / n
                    counts[g] = counts.get(g, 0) + 1
        gmean = {g: sums[g] / counts[g] for g in sums}

        for layer in self.layers:
            n = max(1, len(layer) - 1)

            def key(item):
                i, nid = item
                g = self.group_of.get(nid)
                primary = gmean[g] if g else i / n
                return (primary, i)

            layer[:] = [nid for _, nid in sorted(enumerate(layer), key=key)]
            for i, nid in enumerate(layer):
                self.nodes[nid].order = i

    # -- 5. cross-axis coordinates -----------------------------------------
    def assign_cross(self) -> None:
        def cross_size(n: LNode) -> float:
            if n.dummy:
                return DUMMY_SIZE
            return n.w if not self.horizontal else n.h

        def gap_between(a_nid: str, b_nid: str) -> float:
            # Larger gap across a group boundary so highlight boxes stay apart.
            ga, gb = self.group_of.get(a_nid), self.group_of.get(b_nid)
            return SIBLING_GAP + (GROUP_GAP if ga != gb else 0.0)

        # Initial packed positions per layer.
        for layer in self.layers:
            x = 0.0
            prev = None
            for nid in layer:
                n = self.nodes[nid]
                half = cross_size(n) / 2
                x += half + (gap_between(prev, nid) if prev else 0.0)
                n.cross = x
                x += half
                prev = nid

        up: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        down: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            for a, b in zip(e.chain, e.chain[1:]):
                down[a].append(b)
                up[b].append(a)

        def resolve(layer: List[str]) -> None:
            # left-to-right then right-to-left to enforce min separation.
            for i in range(1, len(layer)):
                a, b = self.nodes[layer[i - 1]], self.nodes[layer[i]]
                min_d = cross_size(a) / 2 + cross_size(b) / 2 + gap_between(layer[i - 1], layer[i])
                if b.cross - a.cross < min_d:
                    b.cross = a.cross + min_d
            for i in range(len(layer) - 2, -1, -1):
                a, b = self.nodes[layer[i]], self.nodes[layer[i + 1]]
                min_d = cross_size(a) / 2 + cross_size(b) / 2 + gap_between(layer[i], layer[i + 1])
                if b.cross - a.cross < min_d:
                    a.cross = b.cross - min_d

        def align(neigh: Dict[str, List[str]], layer_order: List[int]) -> None:
            for li in layer_order:
                layer = self.layers[li]
                for nid in layer:
                    ns = neigh[nid]
                    if ns:
                        self.nodes[nid].cross = sum(self.nodes[x].cross for x in ns) / len(ns)
                resolve(layer)

        for it in range(8):
            if it % 2 == 0:
                align(up, list(range(len(self.layers))))
            else:
                align(down, list(range(len(self.layers) - 1, -1, -1)))

        # Compaction: nodes with no neighbours above or below tend to drift far
        # from their siblings, leaving big gaps (and oversized cluster boxes).
        # Pull each such "free" node next to its layer siblings.
        for _ in range(4):
            for layer in self.layers:
                for i, nid in enumerate(layer):
                    if up[nid] or down[nid]:
                        continue
                    n = self.nodes[nid]
                    left = self.nodes[layer[i - 1]] if i > 0 else None
                    right = self.nodes[layer[i + 1]] if i < len(layer) - 1 else None
                    if left and right:
                        n.cross = (left.cross + right.cross) / 2
                    elif left:
                        n.cross = left.cross + cross_size(left) / 2 + cross_size(n) / 2 + SIBLING_GAP
                    elif right:
                        n.cross = right.cross - cross_size(right) / 2 - cross_size(n) / 2 - SIBLING_GAP
                resolve(layer)

    # -- 6. project to pixels ----------------------------------------------
    def finalize(self) -> Layout:
        # Main-axis position per rank from per-rank max main-size.
        def main_size(n: LNode) -> float:
            if n.dummy:
                return DUMMY_SIZE
            return n.h if not self.horizontal else n.w

        rank_main: List[float] = []
        acc = 0.0
        for li, layer in enumerate(self.layers):
            big = max((main_size(self.nodes[nid]) for nid in layer), default=DUMMY_SIZE)
            acc += big / 2
            rank_main.append(acc)
            acc += big / 2 + LAYER_GAP

        for layer in self.layers:
            for nid in layer:
                n = self.nodes[nid]
                n.main = rank_main[n.rank]

        # Normalise cross so the minimum is at MARGIN.
        min_cross = min((n.cross - (n.w if not self.horizontal else n.h) / 2)
                        for n in self.nodes.values())
        shift = MARGIN - min_cross
        for n in self.nodes.values():
            n.cross += shift

        # Map (cross, main) -> (x, y) depending on direction.
        placed: Dict[str, PlacedNode] = {}
        for n in self.nodes.values():
            if n.dummy:
                continue
            if self.d.direction == Direction.TB:
                x, y = n.cross, n.main + MARGIN
            elif self.d.direction == Direction.BT:
                x, y = n.cross, (rank_main[-1] - n.main) + MARGIN
            elif self.d.direction == Direction.LR:
                x, y = n.main + MARGIN, n.cross
            else:  # RL
                x, y = (rank_main[-1] - n.main) + MARGIN, n.cross
            placed[n.id] = PlacedNode(id=n.id, x=x, y=y, w=n.w, h=n.h, lines=n.lines)

        def pixel(nid: str) -> Tuple[float, float]:
            n = self.nodes[nid]
            if self.d.direction == Direction.TB:
                return n.cross, n.main + MARGIN
            if self.d.direction == Direction.BT:
                return n.cross, (rank_main[-1] - n.main) + MARGIN
            if self.d.direction == Direction.LR:
                return n.main + MARGIN, n.cross
            return (rank_main[-1] - n.main) + MARGIN, n.cross

        placed_edges: List[PlacedEdge] = []
        for e in self.edges:
            pts = [pixel(nid) for nid in e.chain]
            src, tgt = e.chain[0], e.chain[-1]
            if e.reversed:
                pts = list(reversed(pts))
                src, tgt = e.chain[-1], e.chain[0]
            placed_edges.append(PlacedEdge(source=src, target=tgt, points=pts, reversed=e.reversed))

        # Canvas size.
        max_x = max((p.x + p.w / 2 for p in placed.values()), default=2 * MARGIN)
        max_y = max((p.y + p.h / 2 for p in placed.values()), default=2 * MARGIN)
        width = max_x + MARGIN
        height = max_y + MARGIN

        groups = self._place_groups(placed)
        return Layout(width=width, height=height, nodes=placed, edges=placed_edges, groups=groups)

    def _place_groups(self, placed: Dict[str, PlacedNode]) -> List[PlacedGroup]:
        members: Dict[str, List[str]] = {}
        for n in self.d.nodes:
            if n.group:
                members.setdefault(n.group, []).append(n.id)
        out: List[PlacedGroup] = []
        for g in self.d.groups:
            ids = [i for i in members.get(g.id, []) if i in placed]
            if not ids:
                continue
            xs0 = min(placed[i].x - placed[i].w / 2 for i in ids)
            ys0 = min(placed[i].y - placed[i].h / 2 for i in ids)
            xs1 = max(placed[i].x + placed[i].w / 2 for i in ids)
            ys1 = max(placed[i].y + placed[i].h / 2 for i in ids)
            out.append(PlacedGroup(
                id=g.id,
                x=xs0 - GROUP_PAD,
                y=ys0 - GROUP_PAD - 18,  # extra room for the group label
                w=(xs1 - xs0) + 2 * GROUP_PAD,
                h=(ys1 - ys0) + 2 * GROUP_PAD + 18,
            ))
        return out


def layout_diagram(diagram: Diagram, measure=None) -> Layout:
    eng = _Engine(diagram, measure=measure)
    eng.build()
    eng.break_cycles()
    eng.assign_ranks()
    eng.add_dummies()
    eng.order_layers()
    eng.assign_cross()
    return eng.finalize()


# ---------------------------------------------------------------------------
# Nested-cluster layout: each group is laid out as a self-contained unit, the
# groups (as super-nodes) + the ungrouped nodes are arranged together, then the
# group internals are dropped back in. This makes every cluster a fully
# disjoint region.
# ---------------------------------------------------------------------------
def _seg_hits_box(a, b, box, samples: int = 40) -> bool:
    """True if segment a-b passes through the (already-inflated) box interior."""
    x0, y0, x1, y1 = box
    for i in range(1, samples):
        t = i / samples
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def _route_around(a, b, boxes):
    """Route a-b as a poly-line that detours around obstacle boxes (so edges
    never pass behind nodes). Each box is (x0,y0,x1,y1), already inflated."""
    path = [a, b]
    for _ in range(10):
        hit = None
        for i in range(len(path) - 1):
            for box in boxes:
                if _seg_hits_box(path[i], path[i + 1], box):
                    hit = (i, box)
                    break
            if hit:
                break
        if not hit:
            break
        i, (x0, y0, x1, y1) = hit
        p, q = path[i], path[i + 1]
        # detour through whichever box corner adds the least length
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        best = min(corners, key=lambda c: math.hypot(c[0] - p[0], c[1] - p[1])
                   + math.hypot(q[0] - c[0], q[1] - c[1]))
        if best in path:           # avoid an infinite loop
            break
        path.insert(i + 1, best)
    return path


def _sublayout(diagram: Diagram, member_ids, sizes, node_by_id) -> Layout:
    mset = set(member_ids)
    nodes = [node_by_id[i] for i in member_ids]
    edges = [e for e in diagram.edges if e.source in mset and e.target in mset]
    sub = Diagram(nodes=nodes, edges=edges, groups=[],
                  direction=diagram.direction, font_size=diagram.font_size)
    return layout_diagram(sub, measure=lambda n, fs: sizes[n.id])


def layout_clustered(diagram: Diagram, measure=None) -> Layout:
    if measure is None:
        def measure(n, fs):
            w, h, _ = estimate_size(n.label, n.shape, fs, bool(n.icon))
            return w, h

    node_by_id = {n.id: n for n in diagram.nodes}
    active = [g for g in diagram.groups
              if any(n.group == g.id for n in diagram.nodes)]
    if not active:
        return layout_diagram(diagram, measure=measure)

    sizes = {n.id: measure(n, diagram.font_size) for n in diagram.nodes}
    members = {g.id: [n.id for n in diagram.nodes if n.group == g.id] for g in active}
    grouped = {i for ids in members.values() for i in ids}
    ungrouped = [n for n in diagram.nodes if n.id not in grouped]

    # 1. lay each group out on its own
    sub: Dict[str, Layout] = {}
    gsize: Dict[str, Tuple[float, float]] = {}
    for g in active:
        s = _sublayout(diagram, members[g.id], sizes, node_by_id)
        sub[g.id] = s
        gsize[g.id] = (s.width + 2 * GROUP_PAD, s.height + 2 * GROUP_PAD)

    # 2. arrange groups (as super-nodes) + ungrouped nodes
    def rep(nid: str) -> str:
        grp = node_by_id[nid].group
        return f"__g_{grp}" if grp in members else nid

    qnodes = [Node(id=f"__g_{g.id}", label=g.id) for g in active] + list(ungrouped)
    qsize = {f"__g_{g.id}": gsize[g.id] for g in active}
    qsize.update({n.id: sizes[n.id] for n in ungrouped})
    seen, qedges = set(), []
    for e in diagram.edges:
        if e.source not in node_by_id or e.target not in node_by_id:
            continue
        a, b = rep(e.source), rep(e.target)
        if a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        qedges.append(Edge(source=a, target=b))
    quotient = Diagram(nodes=qnodes, edges=qedges, groups=[],
                       direction=diagram.direction, font_size=diagram.font_size)
    ql = layout_diagram(quotient, measure=lambda n, fs: qsize[n.id])

    # 3. drop group internals back in, centred on their super-node
    placed: Dict[str, PlacedNode] = {}
    for g in active:
        sup = ql.nodes[f"__g_{g.id}"]
        s = sub[g.id]
        ox, oy = sup.x - s.width / 2, sup.y - s.height / 2
        for nid, pn in s.nodes.items():
            placed[nid] = PlacedNode(id=nid, x=ox + pn.x, y=oy + pn.y,
                                     w=pn.w, h=pn.h, lines=pn.lines)
    for n in ungrouped:
        if n.id in ql.nodes:
            placed[n.id] = ql.nodes[n.id]

    # 4. edges between real node centres, routed AROUND other nodes so a line
    #    never passes behind a node.
    inflate = SIBLING_GAP * 0.45
    boxes = {nid: (p.x - p.w / 2 - inflate, p.y - p.h / 2 - inflate,
                   p.x + p.w / 2 + inflate, p.y + p.h / 2 + inflate)
             for nid, p in placed.items()}
    pedges: List[PlacedEdge] = []
    for e in diagram.edges:
        if e.source in placed and e.target in placed:
            ps, pt = placed[e.source], placed[e.target]
            obstacles = [b for nid, b in boxes.items() if nid not in (e.source, e.target)]
            pts = _route_around((ps.x, ps.y), (pt.x, pt.y), obstacles)
            pedges.append(PlacedEdge(source=e.source, target=e.target,
                                     points=pts, reversed=False))

    # 5. group boxes from their (now contiguous) members
    gplaced: List[PlacedGroup] = []
    for g in active:
        ids = [i for i in members[g.id] if i in placed]
        if not ids:
            continue
        x0 = min(placed[i].x - placed[i].w / 2 for i in ids) - GROUP_PAD
        y0 = min(placed[i].y - placed[i].h / 2 for i in ids) - GROUP_PAD
        x1 = max(placed[i].x + placed[i].w / 2 for i in ids) + GROUP_PAD
        y1 = max(placed[i].y + placed[i].h / 2 for i in ids) + GROUP_PAD
        gplaced.append(PlacedGroup(id=g.id, x=x0, y=y0, w=x1 - x0, h=y1 - y0))

    # 6. normalise to a positive canvas, leaving room above for group labels
    label_room = diagram.font_size * 1.7
    minx = min([p.x - p.w / 2 for p in placed.values()]
               + [g.x for g in gplaced]) - MARGIN
    miny = min([p.y - p.h / 2 for p in placed.values()]
               + [g.y - label_room for g in gplaced]) - MARGIN
    dx, dy = -minx, -miny
    for p in placed.values():
        p.x += dx
        p.y += dy
    for e in pedges:
        e.points = [(x + dx, y + dy) for (x, y) in e.points]
    for g in gplaced:
        g.x += dx
        g.y += dy
    maxx = max([p.x + p.w / 2 for p in placed.values()] + [g.x + g.w for g in gplaced])
    maxy = max([p.y + p.h / 2 for p in placed.values()] + [g.y + g.h for g in gplaced])
    return Layout(width=maxx + MARGIN, height=maxy + MARGIN,
                  nodes=placed, edges=pedges, groups=gplaced)
