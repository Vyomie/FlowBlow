# HTTP API Reference

Run locally:

```bash
uvicorn flowblow.api:app --reload
```

Interactive docs are available at `/docs` and `/redoc`.

## Endpoints

### `GET /`

Interactive playground. Paste a diagram spec, render it, and inspect the HTML
diagram in the browser.

### `POST /render.html` → `text/html`

Render a diagram spec to a standalone HTML document.

```bash
curl -X POST "http://localhost:8000/render.html" \
  -H 'Content-Type: application/json' \
  -d '{
    "nodes": [{"id":"a","label":"Start","shape":"stadium"},
              {"id":"b","label":"$E=mc^2$"}],
    "edges": [{"from":"a","to":"b","label":"go"}]
  }' > diagram.html
```

### `GET /examples/{name}.html` → `text/html`

Render one bundled example: `simple`, `algorithm`, or `architecture`.

### `GET /healthz` → `application/json`

Liveness probe: `{"status":"ok","version":"..."}`.

## Errors

Invalid specs return `400` with a JSON `detail` message. Pydantic validation
errors return `422` with field-level errors.

## Python

```python
from flowblow import render_html

html = render_html(spec)
```

## CLI

```bash
python -m flowblow spec.json -o out.html
```
