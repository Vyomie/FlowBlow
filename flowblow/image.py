"""PNG export -- pure Python via Pillow (no browser).

``render_png`` lays the diagram out, draws it with the hand-drawn Pillow
renderer (:mod:`flowblow.raster`), scales it to fill a 16:9 (or any) frame and
returns PNG bytes on a transparent background by default.
"""
from __future__ import annotations

from typing import Optional, Union

from . import build_diagram
from .models import Diagram
from .raster import render_png_bytes


def render_png(
    spec: Union[dict, Diagram],
    width: int = 1080,
    height: int = 1920,
    scale: float = 2.0,
    transparent: bool = True,
    pad_frac: float = 0.035,
    supersample: int = 2,
    output: Optional[str] = None,
) -> bytes:
    """Render ``spec`` to PNG bytes.

    * ``width`` x ``height`` -- frame size in logical px (default 1080x1920 = 9:16)
    * ``scale``              -- output pixel multiplier (2.0 -> 3840x2160)
    * ``transparent``        -- transparent background (else the paper colour)
    * ``pad_frac``           -- empty margin around the diagram, as a fraction
    * ``supersample``        -- anti-aliasing oversample factor (1-3)
    * ``output``             -- if given, also write the PNG to this path
    """
    diagram = build_diagram(spec)
    png = render_png_bytes(diagram, width=width, height=height, scale=scale,
                           transparent=transparent, pad_frac=pad_frac,
                           supersample=supersample)
    if output:
        with open(output, "wb") as fh:
            fh.write(png)
    return png
