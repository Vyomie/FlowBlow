"""FlowBlow -- generate hand-drawn flow diagrams / architecture diagrams as
pure HTML + CSS + SVG, with LaTeX support, in the Caveat handwriting font.

Quick use::

    from flowblow import render_html

    html = render_html({
        "title": "Hello",
        "direction": "LR",
        "nodes": [{"id": "a", "label": "Start"}, {"id": "b", "label": "$E=mc^2$"}],
        "edges": [{"from": "a", "to": "b", "label": "go"}],
    })
"""
from __future__ import annotations

from typing import Union

from .layout import Layout, layout_diagram
from .models import Diagram, Direction, Edge, Group, Node, Shape
from .render import render

__all__ = [
    "Diagram",
    "Node",
    "Edge",
    "Group",
    "Shape",
    "Direction",
    "Layout",
    "layout_diagram",
    "render",
    "render_html",
    "build_diagram",
]

__version__ = "0.1.0"


def build_diagram(spec: Union[dict, Diagram]) -> Diagram:
    """Coerce a dict (or Diagram) into a validated :class:`Diagram`."""
    if isinstance(spec, Diagram):
        return spec
    return Diagram.model_validate(spec)


def render_html(spec: Union[dict, Diagram]) -> str:
    """Validate ``spec``, lay it out, and return a standalone HTML document."""
    diagram = build_diagram(spec)
    layout = layout_diagram(diagram)
    return render(diagram, layout)

