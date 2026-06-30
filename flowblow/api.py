"""FastAPI application exposing FlowBlow as an HTTP API (PNG output).

Run with::

    uvicorn flowblow.api:app --reload

Endpoints
---------
GET  /                    -> tiny interactive playground (paste JSON, see PNG)
POST /render              -> hand-drawn diagram as image/png  (the main one)
POST /render.html         -> standalone HTML version (LaTeX via MathJax/CDN)
GET  /examples/{name}.png -> render a bundled example to PNG
GET  /healthz             -> liveness probe

The PNG endpoints take optional query params: ``width``, ``height``,
``scale``, ``transparent``.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from . import __version__, render_html
from .image import render_png
from .models import Diagram

app = FastAPI(
    title="FlowBlow",
    version=__version__,
    description="Hand-drawn flow & architecture diagrams as PNG, with LaTeX.",
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/render")
def render_endpoint(
    diagram: Diagram,
    width: int = 1080,
    height: int = 1920,
    scale: float = 2.0,
    transparent: bool = True,
) -> Response:
    """Render a diagram spec to a transparent hand-drawn PNG."""
    try:
        png = render_png(diagram, width=width, height=height, scale=scale,
                         transparent=transparent)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=f"render failed: {exc}") from exc
    return Response(content=png, media_type="image/png")


@app.post("/render.html", response_class=HTMLResponse)
def render_html_endpoint(diagram: Diagram) -> HTMLResponse:
    """Standalone HTML version (handy for live/scalable embedding)."""
    return HTMLResponse(content=render_html(diagram))


@app.get("/examples/{name}.png")
def render_example(name: str, width: int = 1080, height: int = 1920,
                   scale: float = 2.0, transparent: bool = True) -> Response:
    path = EXAMPLES_DIR / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in EXAMPLES_DIR.glob("*.json"))
        raise HTTPException(status_code=404, detail=f"unknown example. try: {available}")
    spec = json.loads(path.read_text())
    png = render_png(spec, width=width, height=height, scale=scale, transparent=transparent)
    return Response(content=png, media_type="image/png")


PLAYGROUND = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>FlowBlow playground</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;display:flex;height:100vh}
 #left{width:38%;display:flex;flex-direction:column;border-right:1px solid #ddd}
 #right{flex:1;background:
   linear-gradient(45deg,#eee 25%,transparent 25%,transparent 75%,#eee 75%) 0 0/24px 24px,
   linear-gradient(45deg,#eee 25%,#fff 25%,#fff 75%,#eee 75%) 12px 12px/24px 24px;
   display:flex;align-items:center;justify-content:center;overflow:auto}
 textarea{flex:1;border:0;padding:14px;font-family:ui-monospace,monospace;font-size:13px;resize:none}
 .bar{padding:10px 14px;background:#2b2b2b;color:#fbf7ee;display:flex;gap:10px;align-items:center}
 .bar b{font-size:18px}
 button{margin-left:auto;background:#ffd6a5;border:0;padding:8px 18px;border-radius:8px;cursor:pointer;font-weight:600}
 img{max-width:100%;max-height:100%}
</style></head><body>
<div id="left">
 <div class="bar"><b>FlowBlow</b> <span>paste a diagram spec</span>
   <button onclick="go()">Render &#9654;</button></div>
 <textarea id="spec"></textarea>
</div>
<div id="right"><img id="out"/></div>
<script>
const sample = {
  title: "Web request lifecycle",
  direction: "LR",
  groups: [{id:"edge",label:"Edge"},{id:"core",label:"Core services"}],
  nodes: [
    {id:"u",label:"User",shape:"circle",icon:"\\uD83D\\uDC64"},
    {id:"cdn",label:"CDN / Cache",shape:"cylinder",group:"edge"},
    {id:"lb",label:"Load Balancer",shape:"hexagon",group:"edge"},
    {id:"api",label:"API $f(x)$",group:"core"},
    {id:"db",label:"Postgres",shape:"cylinder",group:"core"},
    {id:"ok",label:"200 OK",shape:"stadium"}
  ],
  edges: [
    {from:"u",to:"cdn",label:"GET /"},
    {from:"cdn",to:"lb",label:"miss"},
    {from:"lb",to:"api"},
    {from:"api",to:"db",label:"query"},
    {from:"db",to:"api",style:"dashed"},
    {from:"api",to:"ok"}
  ]
};
document.getElementById('spec').value = JSON.stringify(sample,null,2);
async function go(){
  let spec;
  try{ spec = JSON.parse(document.getElementById('spec').value); }
  catch(e){ alert('Invalid JSON: '+e); return; }
  const r = await fetch('/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(spec)});
  if(!r.ok){ alert('Render failed: '+await r.text()); return; }
  const blob = await r.blob();
  document.getElementById('out').src = URL.createObjectURL(blob);
}
go();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def playground() -> HTMLResponse:
    return HTMLResponse(content=PLAYGROUND)
