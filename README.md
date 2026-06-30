# FlowBlow ✍️

Generate **hand-drawn flow & architecture diagrams** as PNGs, straight from Python.

FlowBlow takes a small JSON spec (nodes + edges) and renders a sketchy,
handwritten-style diagram — flowcharts, system architectures, data pipelines,
state machines, whatever you can express as a directed graph. It is **not**
limited to traditional flowcharts.

- 🖋️ **Handwritten look** — everything is set in the *Caveat* font (bundled &
  embedded, no network needed) with jittered, double-stroked "rough" borders.
- ∑ **LaTeX** — inline `$...$` math is rasterised with matplotlib and composited
  into labels. Latin letters/digits/operators render in Caveat; symbols Caveat
  lacks (Greek, ∇, ‖·‖, …) fall back to a math font.
- 🧩 **Real auto-layout** — a from-scratch layered (Sugiyama) engine: cycle
  breaking, longest-path ranking, dummy-node edge routing and crossing
  reduction. Handles cycles and disconnected graphs.
- 🟦 **Shapes & clusters** — rect, rounded, stadium, ellipse, circle, diamond,
  hexagon, parallelogram, cylinder (db), cloud, note — plus labelled group/
  subgraph boxes for architectures.
- 🖼️ **PNG output** — transparent background, scaled to best fill a **16:9**
  frame (configurable). Rendered **purely in Pillow** — no browser, no HTML.

| Flowchart | Architecture | LaTeX |
|---|---|---|
| `examples/png/simple.png` | `examples/png/architecture.png` | `examples/png/algorithm.png` |

## Install

```bash
pip install -r requirements.txt        # Pillow, matplotlib, pydantic (+ fastapi for the API)
```

## Use it

### Python

```python
from flowblow import render_png

spec = {
    "title": "Hello",
    "direction": "LR",
    "nodes": [
        {"id": "a", "label": "Start", "shape": "stadium"},
        {"id": "b", "label": "Compute $E=mc^2$"},
        {"id": "c", "label": "Done", "shape": "stadium", "icon": "✅"},
    ],
    "edges": [
        {"from": "a", "to": "b", "label": "go"},
        {"from": "b", "to": "c"},
    ],
}

png_bytes = render_png(spec, output="hello.png")          # transparent 3840x2160
# render_png(spec, width=2560, height=1440, scale=2, transparent=False)
```

### Command line

```bash
python -m flowblow examples/architecture.json            # -> examples/architecture.png
python -m flowblow spec.json -o out.png --width 2560 --height 1440
python -m flowblow spec.json --html -o out.html          # standalone HTML (LaTeX via MathJax)
cat spec.json | python -m flowblow -                     # stdin
```

### HTTP API

```bash
uvicorn flowblow.api:app --reload
# open http://localhost:8000/          -> interactive playground
# POST http://localhost:8000/render    -> image/png   (body = the JSON spec)
# GET  http://localhost:8000/examples/architecture.png
```

Query params on the PNG endpoints: `width`, `height`, `scale`, `transparent`.

## Spec reference

```jsonc
{
  "title": "My System",
  "direction": "TB",            // TB | BT | LR | RL
  "font_size": 24,
  "accent": "#2b2b2b",          // ink colour
  "groups": [
    { "id": "core", "label": "Core", "color": "#a0c4ff" }
  ],
  "nodes": [
    {
      "id": "api",
      "label": "API  $f(x)$",   // LaTeX allowed
      "shape": "rounded",       // see shapes above
      "group": "core",          // optional cluster membership
      "color": "#caffbf",       // optional fill override
      "icon": "🌐"              // optional emoji shown above the label
    }
  ],
  "edges": [
    { "from": "api", "to": "db", "label": "query",
      "style": "solid",         // solid | dashed | dotted
      "bidirectional": false }
  ]
}
```

`from`/`to` (or `source`/`target`) reference node ids. Cycles and missing
targets are handled gracefully.

## How it works

```
spec ─► models.py ─► layout.py ─► raster.py ─► PNG
        (validate)   (Sugiyama)   (Pillow draw)
                                    └─ content.py  (text/LaTeX/emoji measurement)
                                    └─ mathtex.py  (LaTeX → image, matplotlib)
```

There is also an HTML renderer (`render_html`, `render.py` + `templates.py`)
that emits a self-contained page using SVG + MathJax — handy when you want a
live/scalable/selectable version instead of a raster.

## Tests

```bash
PYTHONPATH=. python tests/test_flowblow.py      # or: python -m pytest -q
```

## Notes & limits

- **Tall single-column flows** can't fill a wide 16:9 frame horizontally; they
  centre with side margins. Pick `--width/--height` to match your shape.
- **Group boxes** are axis-aligned bounding boxes of their members; a cluster
  whose nodes span many layers can overlap a neighbouring cluster.
- The bundled Caveat font is © The Caveat Project Authors, SIL Open Font License.
