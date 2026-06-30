"""Pydantic models describing a FlowBlow diagram specification.

A diagram is just a set of nodes and edges (plus optional groups/clusters).
Because it is a generic directed graph it can describe *anything* -- classic
flowcharts, system architectures, data pipelines, state machines, mind maps...
Labels may contain LaTeX wrapped in ``$...$`` or ``$$...$$``.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Shape(str, Enum):
    """Visual shape of a node."""

    rect = "rect"            # process / generic box
    rounded = "rounded"      # rounded process box
    stadium = "stadium"      # pill -- good for start/end
    ellipse = "ellipse"
    circle = "circle"
    diamond = "diamond"      # decision
    hexagon = "hexagon"      # preparation / special
    parallelogram = "parallelogram"   # input / output
    cylinder = "cylinder"    # database / store
    cloud = "cloud"          # external service / internet
    note = "note"            # folded-corner note / document


class Direction(str, Enum):
    """Primary flow direction."""

    TB = "TB"  # top -> bottom
    BT = "BT"  # bottom -> top
    LR = "LR"  # left -> right
    RL = "RL"  # right -> left


class Node(BaseModel):
    id: str
    label: str = ""
    shape: Shape = Shape.rounded
    group: Optional[str] = None
    color: Optional[str] = Field(
        default=None,
        description="Override fill colour (any CSS colour). Stroke is derived.",
    )
    icon: Optional[str] = Field(
        default=None, description="Optional emoji/short glyph rendered above the label."
    )

    def model_post_init(self, __context) -> None:  # noqa: D401
        if not self.label:
            self.label = self.id


class EdgeStyle(str, Enum):
    solid = "solid"
    dashed = "dashed"
    dotted = "dotted"


class Edge(BaseModel):
    # `source`/`target` are canonical but we accept `from`/`to` aliases below.
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    label: str = ""
    style: EdgeStyle = EdgeStyle.solid
    color: Optional[str] = None
    # Draw an arrow head at the target end (default) and/or source end.
    arrow: bool = True
    bidirectional: bool = False

    model_config = {"populate_by_name": True}


class Group(BaseModel):
    """A cluster / subgraph drawn as a labelled container behind its members."""

    id: str
    label: str = ""
    color: Optional[str] = None

    def model_post_init(self, __context) -> None:  # noqa: D401
        if not self.label:
            self.label = self.id


class Diagram(BaseModel):
    title: str = ""
    direction: Direction = Direction.TB
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)
    groups: List[Group] = Field(default_factory=list)
    # Visual knobs.
    font_size: int = 40
    accent: str = "#2b2b2b"  # ink colour for strokes/text
    paper: str = "#fbf7ee"   # background "paper" colour
    # How to provide the Caveat handwriting font:
    #   "embed"  -> base64-inline it (default; fully self-contained, no network)
    #   "cdn"    -> link Google Fonts (smaller HTML, needs internet)
    #   "system" -> use a local cursive fallback
    font_mode: str = "embed"
    # LaTeX support via MathJax:
    #   "cdn"  -> load MathJax from jsDelivr (default; needs internet)
    #   "none" -> no LaTeX rendering (literal $...$ shown)
    mathjax_mode: str = "cdn"
    sketch: bool = True  # apply the hand-drawn "rough" wobble filter
    transparent: bool = False  # drop the paper background (for PNG export)

    model_config = {"populate_by_name": True}
