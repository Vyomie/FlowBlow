"""Rasterise LaTeX math fragments to RGBA images using matplotlib's *mathtext*.

This needs **no external LaTeX install** -- matplotlib parses the math itself.
We point mathtext's fonts at the vendored Caveat face, so Latin letters,
digits and operators come out handwritten; symbols Caveat lacks (Greek,
nabla, norms, ...) fall back to a math font so they still render.
"""
from __future__ import annotations

import functools
import io
from pathlib import Path
from typing import Tuple

from PIL import Image

_ASSET_DIR = Path(__file__).resolve().parent / "assets"
_NATIVE_FONTSIZE = 64
_NATIVE_DPI = 220
_initialised = False


def _init() -> None:
    global _initialised
    if _initialised:
        return
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager as fm

    for weight in (600, 700):
        f = _ASSET_DIR / f"Caveat-{weight}.ttf"
        if f.exists():
            fm.fontManager.addfont(str(f))

    rc = matplotlib.rcParams
    rc["mathtext.fontset"] = "custom"
    for key in ("rm", "it", "bf", "sf", "tt", "cal"):
        rc[f"mathtext.{key}"] = "Caveat"
    rc["mathtext.fallback"] = "cm"
    rc["text.usetex"] = False
    _initialised = True


@functools.lru_cache(maxsize=512)
def render_math(tex: str, color: str = "#2b2b2b") -> Image.Image:
    """Render ``$...$`` (or bare) LaTeX to a tight, transparent RGBA image.

    The image is rendered large; callers scale it down to the size they need
    (downscaling keeps it crisp).  Returns a 1x1 transparent image on failure.
    """
    _init()
    import matplotlib.pyplot as plt

    body = tex.strip()
    if not (body.startswith("$") and body.endswith("$")):
        body = f"${body}$"

    fig = plt.figure(figsize=(0.01, 0.01))
    try:
        fig.text(0, 0, body, fontsize=_NATIVE_FONTSIZE, color=color)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=_NATIVE_DPI, transparent=True,
                    bbox_inches="tight", pad_inches=0.01)
    except Exception:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    finally:
        plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def math_aspect(tex: str) -> float:
    """Width / height of the rendered math (for measuring before drawing)."""
    im = render_math(tex)
    return im.width / im.height if im.height else 1.0
