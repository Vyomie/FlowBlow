"""Basic smoke tests for FlowBlow.

Run with:  python -m pytest -q   (or just  python tests/test_flowblow.py)
"""
import json
import struct
from pathlib import Path

from flowblow import build_diagram, layout_diagram, render_html
from flowblow.image import render_png

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))


def _png_size(data: bytes):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def test_layout_handles_cycles_and_disconnected():
    spec = {
        "nodes": [{"id": x} for x in "abcd"],
        # a->b->c->a is a cycle; d is disconnected
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                  {"from": "c", "to": "a"}],
    }
    layout = layout_diagram(build_diagram(spec))
    assert len(layout.nodes) == 4
    assert layout.width > 0 and layout.height > 0


def test_render_html_contains_svg():
    spec = {"nodes": [{"id": "a", "label": "Hello $x^2$"}]}
    html = render_html(spec)
    assert "<svg" in html and "node-shape" in html


def test_render_png_is_16_9_and_transparent():
    spec = {
        "title": "T",
        "nodes": [{"id": "a", "label": "Start"}, {"id": "b", "label": "$E=mc^2$"}],
        "edges": [{"from": "a", "to": "b", "label": "go"}],
    }
    png = render_png(spec, width=800, height=450, scale=1, transparent=True)
    w, h = _png_size(png)
    assert (w, h) == (800, 450)
    # 16:9
    assert abs(w / h - 16 / 9) < 1e-6


def test_all_examples_render():
    assert EXAMPLES, "no example specs found"
    for f in EXAMPLES:
        spec = json.loads(f.read_text())
        png = render_png(spec, width=640, height=360, scale=1)
        w, h = _png_size(png)
        assert (w, h) == (640, 360)


if __name__ == "__main__":
    test_layout_handles_cycles_and_disconnected()
    test_render_html_contains_svg()
    test_render_png_is_16_9_and_transparent()
    test_all_examples_render()
    print("all tests passed")
