# Diagram spec reference

A diagram is a JSON object: a set of **nodes** and **edges**, plus optional
**groups** (clusters) and a few visual knobs. It's a directed graph, so it can
describe flowcharts, architectures, pipelines, state machines — anything.

```json
{
  "direction": "TB",
  "groups":  [ { "id": "svc", "label": "Services", "color": "#caffbf" } ],
  "nodes":   [ { "id": "a", "label": "Start", "shape": "stadium" } ],
  "edges":   [ { "from": "a", "to": "b", "label": "go" } ]
}
```

## Diagram (top level)

| field | type | default | notes |
|-------|------|---------|-------|
| `title` | string | `""` | Not drawn on the PNG (kept for the HTML renderer). |
| `direction` | `TB` \| `BT` \| `LR` \| `RL` | `TB` | Primary flow direction. The renderer auto-rotates to whichever orientation best fills the frame. |
| `nodes` | Node[] | `[]` | See below. |
| `edges` | Edge[] | `[]` | See below. |
| `groups` | Group[] | `[]` | Clusters drawn as labelled boxes; laid out as disjoint regions. |
| `font_size` | int | `40` | Base font size in layout units. |
| `accent` | CSS colour | `#2b2b2b` | Ink colour for strokes and text. |
| `paper` | CSS colour | `#fbf7ee` | Background when `transparent=false`. |

## Node

| field | type | default | notes |
|-------|------|---------|-------|
| `id` | string | required | Unique. |
| `label` | string | `id` | May contain inline LaTeX in `$...$` / `$$...$$`. |
| `shape` | Shape | `rounded` | See shapes below. |
| `group` | string | `null` | id of a group this node belongs to. |
| `color` | CSS colour | auto | Fill colour; a pastel is auto-assigned if omitted. |
| `icon` | string | `null` | An emoji drawn above the label (needs a colour-emoji font). |

**Shapes:** `rect`, `rounded`, `stadium`, `ellipse`, `circle`, `diamond`
(decision), `hexagon`, `parallelogram` (I/O), `cylinder` (database/store),
`cloud` (external service), `note` (document).

## Edge

`from`/`to` are the canonical names; `source`/`target` also work.

| field | type | default | notes |
|-------|------|---------|-------|
| `from` / `source` | string | required | Source node id. |
| `to` / `target` | string | required | Target node id. |
| `label` | string | `""` | May contain LaTeX. `yes`/`no` render as a big green **Y** / red **N**. |
| `style` | `solid` \| `dashed` \| `dotted` | `solid` | |
| `color` | CSS colour | ink | |
| `arrow` | bool | `true` | Arrowhead at the target. |
| `bidirectional` | bool | `false` | Also draw an arrowhead at the source. |

## Group (cluster)

| field | type | default | notes |
|-------|------|---------|-------|
| `id` | string | required | Referenced by `node.group`. |
| `label` | string | `id` | Drawn in the group's highlight colour, just above the box. |
| `color` | CSS colour | auto | Highlight colour. |

Each group is laid out as a self-contained unit and placed as a **disjoint
region** — cluster boxes never overlap.

## LaTeX

Latin letters, digits and operators render in the Caveat handwriting font;
symbols Caveat lacks (Greek, ∇, ‖, …) fall back to a math font so they still
render. Examples: `"$E=mc^2$"`, `"Converged? $\\|\\nabla J\\| < \\epsilon$"`.

## A fuller example

```json
{
  "direction": "TB",
  "groups": [
    { "id": "edge", "label": "Edge", "color": "#a0c4ff" },
    { "id": "svc",  "label": "Services", "color": "#caffbf" },
    { "id": "data", "label": "Data Layer", "color": "#ffd6a5" }
  ],
  "nodes": [
    { "id": "client", "label": "Browser / App", "shape": "circle", "icon": "🌐" },
    { "id": "gw",   "label": "API Gateway", "shape": "hexagon", "group": "edge" },
    { "id": "auth", "label": "Auth Service", "group": "svc" },
    { "id": "pg",   "label": "Postgres", "shape": "cylinder", "group": "data" }
  ],
  "edges": [
    { "from": "client", "to": "gw", "label": "HTTPS" },
    { "from": "gw", "to": "auth", "label": "verify" },
    { "from": "auth", "to": "pg", "style": "dashed", "label": "session" }
  ]
}
```
