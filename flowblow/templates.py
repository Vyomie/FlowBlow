"""The standalone HTML shell (CSS + MathJax + the hand-drawn SVG filter)."""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
{font_head}
{mathjax_head}
<style>
  :root {{
    --ink: {ink};
    --paper: {paper};
    --fs: {font_size}px;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    background-color: var(--paper);
    background-image:
      radial-gradient(rgba(120,110,90,0.16) 1.1px, transparent 1.1px);
    background-size: 26px 26px;
    font-family: 'Caveat', 'Comic Sans MS', cursive;
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 28px 18px 60px;
  }}
  .doc-title {{
    font-size: calc(var(--fs) * 2.0);
    font-weight: 700;
    margin: 4px 0 18px;
    letter-spacing: 0.5px;
    text-align: center;
    position: relative;
  }}
  .doc-title::after {{
    content: "";
    display: block;
    width: 62%;
    height: 6px;
    margin: 2px auto 0;
    border-radius: 50%;
    background: radial-gradient(closest-side, rgba(43,43,43,0.55), transparent);
  }}
  #fb-frame {{
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .stage {{
    position: relative;
    width: {width}px;
    height: {height}px;
    max-width: 100%;
  }}
  svg.canvas {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    overflow: visible;
  }}
  .sketch {{ filter: url(#rough); }}
  .node-shape {{
    stroke: var(--ink);
    stroke-width: 2.6;
    stroke-linejoin: round;
    stroke-linecap: round;
    fill-opacity: 0.92;
    paint-order: stroke fill;
  }}
  .edge {{
    fill: none;
    stroke: var(--ink);
    stroke-width: 2.6;
    stroke-linecap: round;
    stroke-linejoin: round;
  }}
  .arrowg .arrow {{ stroke-width: 1.4; stroke-linejoin: round; }}
  .group-box {{
    fill: var(--gcol);
    fill-opacity: 0.10;
    stroke: var(--ink);
    stroke-opacity: 0.45;
    stroke-width: 2.2;
    stroke-dasharray: 4 9;
  }}
  .overlay {{
    position: absolute;
    inset: 0;
    pointer-events: none;
  }}
  .node-label {{
    position: absolute;
    text-align: center;
    line-height: 1.04;
    font-size: var(--fs);
    font-weight: 600;
    color: var(--ink);
  }}
  .node-text mjx-container {{ margin: 0 !important; }}
  .node-icon {{
    font-size: calc(var(--fs) * 1.25);
    line-height: 1;
    margin-bottom: 2px;
    font-family: 'Segoe UI Emoji', 'Apple Color Emoji', sans-serif;
  }}
  .edge-label {{
    position: absolute;
    transform: translate(-50%, -50%);
    font-size: calc(var(--fs) * 0.78);
    font-weight: 600;
    color: var(--ink);
    background: var(--paper);
    padding: 0 7px;
    border-radius: 10px;
    white-space: nowrap;
    box-shadow: 0 0 0 1px rgba(43,43,43,0.06);
  }}
  .group-label {{
    position: absolute;
    font-size: calc(var(--fs) * 0.92);
    font-weight: 700;
    color: var(--ink);
    opacity: 0.72;
    background: var(--paper);
    padding: 0 8px;
    border-radius: 8px;
  }}
  /* Make MathJax render in the handwriting face too. */
  mjx-container, mjx-container * {{
    font-family: 'Caveat', cursive !important;
    font-weight: 600 !important;
  }}
{mode_css}
</style>
</head>
<body>
 <div id="fb-frame">
  {heading_block}
  <div class="stage">
    <svg class="canvas" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">
      <defs>
        <filter id="rough" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.009 0.013"
                        numOctaves="2" seed="11" result="n"/>
          <feDisplacementMap in="SourceGraphic" in2="n" scale="4.2"
                             xChannelSelector="R" yChannelSelector="G"/>
        </filter>
      </defs>
      <g class="{sketch_class}">
{svg_body}
      </g>
    </svg>
    <div class="overlay">
{overlay_body}
    </div>
  </div>
 </div>
{fit_script}
</body>
</html>
"""
