"""Vendored asset handling -- embeds the Caveat handwriting font.

The font files live in ``flowblow/assets/*.ttf`` (a subset of Google Fonts'
Caveat, SIL Open Font License).  Embedding them as base64 data-URIs makes every
generated diagram fully self-contained: the handwritten look works with **no
network access at all**.
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path

_ASSET_DIR = Path(__file__).resolve().parent / "assets"

# weight -> filename
_FONT_FILES = {
    600: "Caveat-600.ttf",
    700: "Caveat-700.ttf",
}


@functools.lru_cache(maxsize=None)
def _font_data_uri(filename: str) -> str:
    raw = (_ASSET_DIR / filename).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:font/ttf;base64,{b64}"


@functools.lru_cache(maxsize=1)
def embedded_font_css() -> str:
    """`@font-face` rules with the Caveat font inlined as base64 data URIs."""
    rules = []
    for weight, fname in _FONT_FILES.items():
        uri = _font_data_uri(fname)
        rules.append(
            "@font-face{"
            "font-family:'Caveat';font-style:normal;font-display:swap;"
            f"font-weight:{weight};src:url({uri}) format('truetype');"
            "}"
        )
    return "\n".join(rules)


GOOGLE_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;500;600;700'
    '&display=swap" rel="stylesheet">'
)


def font_head(mode: str) -> str:
    """Return the <head> markup that provides the Caveat font.

    * ``embed``  -> inline base64 @font-face (default, self-contained)
    * ``cdn``    -> Google Fonts <link> (smaller output, needs network)
    * ``system`` -> nothing (fall back to local cursive/Comic Sans)
    """
    if mode == "embed":
        return f"<style>\n{embedded_font_css()}\n</style>"
    if mode == "cdn":
        return GOOGLE_FONT_LINK
    return "<!-- font: system fallback -->"
