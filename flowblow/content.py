"""Rich-label measurement & layout for the Pillow renderer.

A node/edge label can mix plain text (Caveat), inline LaTeX ($...$) and a
leading emoji icon.  This module tokenises a label, wraps it to a maximum
width and produces a resolution-independent :class:`Block` describing where
each run sits.  ``raster.py`` then draws that block at whatever scale it wants.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import ImageFont

from .mathtex import math_aspect

_ASSET_DIR = Path(__file__).resolve().parent / "assets"
_EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_EMOJI_NATIVE = 109  # NotoColorEmoji bitmap strike size

_MATH_HEIGHT_FACTOR = 1.18   # math glyph height relative to text height
_LINE_SPACING = 1.06


@functools.lru_cache(maxsize=256)
def get_font(weight: int, px: int) -> ImageFont.FreeTypeFont:
    px = max(1, int(round(px)))
    return ImageFont.truetype(str(_ASSET_DIR / f"Caveat-{weight}.ttf"), px)


@functools.lru_cache(maxsize=8)
def _emoji_font() -> Optional[ImageFont.FreeTypeFont]:
    try:
        return ImageFont.truetype(_EMOJI_FONT, _EMOJI_NATIVE)
    except Exception:
        return None


@dataclass
class Run:
    kind: str          # "text" | "math" | "icon"
    payload: str       # text string, tex source, or emoji char
    w: float
    h: float
    x: float = 0.0     # x within its line (left-aligned)


@dataclass
class Line:
    runs: List[Run] = field(default_factory=list)
    w: float = 0.0
    h: float = 0.0


@dataclass
class Block:
    lines: List[Line] = field(default_factory=list)
    w: float = 0.0
    h: float = 0.0
    size: float = 24.0   # the font size the block was measured at


_TOKEN_RE = re.compile(r"(\$\$.*?\$\$|\$.*?\$)", re.S)


def _tokenise(text: str):
    """Yield ('word'|'math'|'break', value) tokens, splitting out math spans."""
    for part in _TOKEN_RE.split(text):
        if not part:
            continue
        if part.startswith("$"):
            yield ("math", part)
        else:
            # split plain text into words and hard line breaks
            for chunk in re.split(r"(\n)", part):
                if chunk == "\n":
                    yield ("break", "")
                else:
                    for word in chunk.split():
                        yield ("word", word)


def layout_block(text: str, size: float, weight: int = 600,
                 max_width: float = 1e9, icon: Optional[str] = None) -> Block:
    """Measure and wrap ``text`` into a :class:`Block` at the given font size."""
    font = get_font(weight, max(1, int(round(size))))
    ascent, descent = font.getmetrics()
    text_h = ascent + descent
    math_h = text_h * _MATH_HEIGHT_FACTOR
    space_w = font.getlength(" ")

    lines: List[Line] = []
    cur = Line()

    def width_of(line: Line) -> float:
        if not line.runs:
            return 0.0
        return sum(r.w for r in line.runs) + space_w * (len(line.runs) - 1)

    def flush() -> None:
        nonlocal cur
        if cur.runs:
            cur.w = width_of(cur)
            cur.h = max(r.h for r in cur.runs)
            lines.append(cur)
        cur = Line()

    # optional icon as its own centred line on top
    if icon and _emoji_font() is not None:
        ih = text_h * 1.35
        lines.append(Line(runs=[Run("icon", icon, ih, ih)], w=ih, h=ih))

    for kind, val in _tokenise(text):
        if kind == "break":
            flush()
            continue
        if kind == "word":
            run = Run("text", val, font.getlength(val), text_h)
        else:  # math
            run = Run("math", val, math_h * math_aspect(val), math_h)
        tentative = width_of(cur) + (space_w if cur.runs else 0) + run.w
        if cur.runs and tentative > max_width:
            flush()
        cur.runs.append(run)
    flush()

    # assign x positions within each line (left aligned; centring is at draw)
    for ln in lines:
        x = 0.0
        for r in ln.runs:
            r.x = x
            x += r.w + space_w

    block = Block(lines=lines)
    block.w = max((ln.w for ln in lines), default=0.0)
    block.h = sum(ln.h for ln in lines) * _LINE_SPACING
    return block


@functools.lru_cache(maxsize=256)
def render_emoji(char: str):
    """Render a single emoji to a tight RGBA image (native size), or None."""
    font = _emoji_font()
    if font is None:
        return None
    from PIL import Image, ImageDraw
    try:
        img = Image.new("RGBA", (_EMOJI_NATIVE * 2, _EMOJI_NATIVE * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((4, 4), char, font=font, embedded_color=True)
        bbox = img.getbbox()
        return img.crop(bbox) if bbox else None
    except Exception:
        return None
