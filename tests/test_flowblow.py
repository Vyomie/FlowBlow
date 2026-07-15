"""Basic smoke tests for FlowBlow.

Run with:  python -m pytest -q   (or just  python tests/test_flowblow.py)
"""
import json
from pathlib import Path

from flowblow import build_diagram, layout_diagram, render_html

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))


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


def test_all_examples_render():
    assert EXAMPLES, "no example specs found"
    for f in EXAMPLES:
        spec = json.loads(f.read_text())
        html = render_html(spec)
        assert "<svg" in html and "fb-frame" in html


if __name__ == "__main__":
    test_layout_handles_cycles_and_disconnected()
    test_render_html_contains_svg()
    test_all_examples_render()
    print("all tests passed")
