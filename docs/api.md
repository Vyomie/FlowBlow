# HTTP API reference

Run locally:

```bash
uvicorn flowblow.api:app --reload      # http://127.0.0.1:8000
```

Interactive docs are auto-generated at `/docs` (Swagger) and `/redoc`.

## Endpoints

### `GET /`
The interactive playground — paste a diagram spec, hit **Render**, see the PNG.

### `POST /render` → `image/png`
Render a diagram spec (see [spec.md](spec.md)) to a transparent hand-drawn PNG.

Query parameters (all optional):

| param | default | meaning |
|-------|---------|---------|
| `width` | `1080` | frame width in logical px |
| `height` | `1920` | frame height in logical px (default is 9:16 portrait) |
| `scale` | `2.0` | output pixel multiplier (2 → 2160×3840) |
| `transparent` | `true` | transparent background (else the `paper` colour) |

```bash
curl -X POST "http://localhost:8000/render?width=1600&height=900" \
  -H 'Content-Type: application/json' \
  -d '{
    "nodes": [{"id":"a","label":"Start","shape":"stadium"},
              {"id":"b","label":"$E=mc^2$"}],
    "edges": [{"from":"a","to":"b","label":"go"}]
  }' -o diagram.png
```

### `POST /render.html` → `text/html`
Same diagram as a standalone HTML document (LaTeX via MathJax, Caveat font
embedded). Handy for scalable/embeddable output.

### `GET /examples/{name}.png` → `image/png`
Render one of the bundled examples (`simple`, `algorithm`, `architecture`).
Accepts the same query params as `/render`.

### `GET /healthz` → `application/json`
Liveness probe: `{"status": "ok", "version": "..."}`.

## Errors

Invalid specs return `400` with a JSON `detail` message. A spec that fails
Pydantic validation (e.g. missing `id`) returns `422` with field-level errors.

## Using it from Python instead

You don't need the HTTP server — the library is directly importable:

```python
from flowblow import render_png, render_html

render_png(spec, output="out.png")     # bytes, transparent 9:16 by default
html = render_html(spec)               # standalone HTML string
```

Or the CLI:

```bash
python -m flowblow spec.json -o out.png
python -m flowblow spec.json --html -o out.html
python -m flowblow spec.json --width 1600 --height 900 --opaque
```
