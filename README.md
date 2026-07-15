# FlowBlow

Generate hand-drawn flow and architecture diagrams as standalone HTML/SVG from
plain JSON specs. The output uses SVG shapes, HTML labels, the Caveat handwriting
font, and MathJax for LaTeX.

## Install

```bash
pip install -r requirements.txt
```

## Python

```python
from flowblow import render_html

html = render_html({
    "direction": "TB",
    "nodes": [
        {"id": "s", "label": "Start", "shape": "stadium"},
        {"id": "c", "label": "Converged? $\\|\\nabla J\\| < \\epsilon$", "shape": "diamond"},
        {"id": "d", "label": "Return $\\theta^{*}$", "shape": "stadium"},
    ],
    "edges": [
        {"from": "s", "to": "c"},
        {"from": "c", "to": "d", "label": "yes"},
    ],
})
```

## CLI

```bash
python -m flowblow examples/architecture.json
python -m flowblow spec.json -o out.html
```

## HTTP API

```bash
uvicorn flowblow.api:app --reload
# GET  /                         interactive playground
# POST /render.html              standalone HTML document
# GET  /examples/{name}.html     bundled example
# GET  /healthz                  liveness
```

Full API reference: [docs/api.md](docs/api.md).

## Deploy

```bash
gcloud run deploy flowblow --source . --region us-central1 \
  --allow-unauthenticated --memory 512Mi --cpu 1 --concurrency 40
```

Full guide: [docs/deploy.md](docs/deploy.md).

## Diagram Spec

| field | meaning |
| --- | --- |
| `direction` | `TB`, `BT`, `LR`, or `RL` |
| `nodes[]` | `id`, `label`, `shape`, `color`, `group`, `icon` |
| `edges[]` | `from`/`to`, `label`, `style`, `color`, `bidirectional` |
| `groups[]` | `id`, `label`, `color` |
| `font_size` | base size, default `40` |

Labels may contain inline LaTeX in `$...$` or `$$...$$`. Full reference:
[docs/spec.md](docs/spec.md).

## How It Works

1. Estimate node sizes from text and shape.
2. Layout the directed graph with a layered Sugiyama-style engine.
3. Route edges around node boxes.
4. Render a standalone HTML document with SVG strokes and HTML labels.

## Tests

```bash
python -m pytest -q
```
