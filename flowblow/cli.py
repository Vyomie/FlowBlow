"""Command-line interface: render a diagram JSON file to a PNG (or HTML).

Usage::

    python -m flowblow spec.json                 # -> spec.png (transparent, 16:9)
    python -m flowblow spec.json -o out.png
    python -m flowblow spec.json --html -o out.html
    python -m flowblow spec.json --width 2560 --height 1440 --scale 2
    cat spec.json | python -m flowblow -          # stdin -> flowblow-out.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(prog="flowblow", description="Render a FlowBlow diagram.")
    p.add_argument("spec", help="diagram JSON file, or '-' for stdin")
    p.add_argument("-o", "--output", help="output path (default: alongside input)")
    p.add_argument("--html", action="store_true", help="emit standalone HTML instead of PNG")
    p.add_argument("--width", type=int, default=1080, help="frame width  (default 1080)")
    p.add_argument("--height", type=int, default=1920, help="frame height (default 1920)")
    p.add_argument("--scale", type=float, default=2.0, help="pixel multiplier (default 2.0)")
    p.add_argument("--opaque", action="store_true", help="paper background instead of transparent")
    args = p.parse_args(argv)

    if args.spec == "-":
        spec = json.load(sys.stdin)
        default = Path("flowblow-out.html" if args.html else "flowblow-out.png")
    else:
        in_path = Path(args.spec)
        spec = json.loads(in_path.read_text())
        default = in_path.with_suffix(".html" if args.html else ".png")
    out = Path(args.output) if args.output else default

    if args.html:
        from . import render_html
        out.write_text(render_html(spec))
    else:
        from .image import render_png
        render_png(spec, width=args.width, height=args.height, scale=args.scale,
                   transparent=not args.opaque, output=str(out))

    size = out.stat().st_size
    print(f"wrote {out}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
