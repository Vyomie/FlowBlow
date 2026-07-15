"""Command-line interface: render a diagram JSON file to standalone HTML.

Usage::

    python -m flowblow spec.json                 # -> spec.html
    python -m flowblow spec.json -o out.html
    cat spec.json | python -m flowblow -          # stdin -> flowblow-out.html
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
    args = p.parse_args(argv)

    if args.spec == "-":
        spec = json.load(sys.stdin)
        default = Path("flowblow-out.html")
    else:
        in_path = Path(args.spec)
        spec = json.loads(in_path.read_text())
        default = in_path.with_suffix(".html")
    out = Path(args.output) if args.output else default

    from . import render_html
    out.write_text(render_html(spec))

    size = out.stat().st_size
    print(f"wrote {out}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
