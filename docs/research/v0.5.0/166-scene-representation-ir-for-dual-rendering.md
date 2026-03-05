# Research: Scene Representation IR for Dual File/Window Rendering

**Issue:** #166
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Decision reached

---

## Summary

A single `Scene` dataclass is sufficient for both file-based (PNG/SVG) and future
windowed (Tk) rendering. All renderers consume the same IR; no data-flow fork is
needed. The module boundary is: `plotter/` produces a `Scene`, `renderer/` consumes
it. This satisfies the v0.5.x constraint and leaves the pipeline open for v0.7.x
without duplication.

---

## Q1 — Can one scene IR serve both file and window rendering?

**Decision: Yes — a single `Scene` struct.**

The key insight is that both raster (PNG), vector (SVG), and interactive (Tk canvas)
renderers need the same abstract geometry:

- A list of polyline **segments** (gaps between segments represent discontinuities).
- **Axis bounds** so each renderer can map world coordinates to device coordinates.
- **Tick positions and labels** so each renderer can draw axis annotations
  independently.
- **Image dimensions** so each renderer knows the output size.

None of these fields are renderer-specific. The renderers differ only in *how* they
emit that geometry (pixel drawing vs. SVG path elements vs. canvas lines). The scene
itself is device-independent.

This mirrors the matplotlib `Figure`/`Axes` model at small scale: the `Axes` object
holds data and geometry; the backend (Agg, SVG, PDF, TkAgg) holds the drawing
primitives. Our scale is much smaller, but the principle is the same.

---

## Q2 — Does SVG's vector nature require a separate scene type?

**Decision: No.**

SVG paths are produced from the same polyline segments that PNG uses to draw pixels.
The SVG renderer iterates segments and emits `<polyline points="…"/>` elements.
The PNG renderer iterates the same segments and draws lines between sample points.
Both consume `scene.segments` identically; neither needs extra geometric information.

A `text` element in SVG and a pixel-drawn tick label in PNG both come from
`scene.x_ticks` / `scene.y_ticks`. The difference is rendering mechanics, not data.

---

## Q3 — Recommended `Scene` fields

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Scene:
    # Canvas size
    width: int
    height: int

    # World-space bounds (after 10% padding)
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    # Axis tick marks: list of (world_value, display_label)
    x_ticks: tuple[tuple[float, str], ...]
    y_ticks: tuple[tuple[float, str], ...]

    # Curve geometry: list of continuous polylines.
    # Each polyline is a list of (x, y) world-coordinate pairs.
    # A gap in the curve (discontinuity) is represented as two separate polylines.
    segments: tuple[tuple[tuple[float, float], ...], ...]
```

`frozen=True` makes the scene safely shareable between threads (relevant if a future
Tk renderer runs its event loop on a separate thread). Tuples rather than lists
enforce immutability without extra runtime cost.

The coordinate type is **world space** throughout. Every renderer applies its own
world→device transform (`(x - x_min) / (x_max - x_min) * width`, etc.). This keeps
the scene free of pixel or SVG-unit values.

---

## Q4 — Renderer interface contract

```python
from typing import Protocol
from pathlib import Path

class Renderer(Protocol):
    def render(self, scene: "Scene", output: Path) -> None:
        """Write or display `scene`. Raises OSError on write failure."""
        ...
```

Concrete implementations for v0.5.0:

| Class | Module | Trigger |
|---|---|---|
| `PngRenderer` | `calc/renderer/png.py` | `output.suffix == ".png"` |
| `SvgRenderer` | `calc/renderer/svg.py` | `output.suffix == ".svg"` |

Planned for v0.7.x:

| Class | Module | Trigger |
|---|---|---|
| `TkRenderer` | `calc/renderer/tk.py` | `--window` flag |

The `TkRenderer.render` method will open a Tk window and draw the same segments and
ticks from the same `Scene`. The plotter never needs to know which renderer is active.

---

## Q5 — Module boundary

```
calc/
  plotter.py        # evaluates expression → Scene (owns curve math)
  renderer/
    __init__.py     # Renderer Protocol; dispatch by extension
    png.py          # PngRenderer
    svg.py          # SvgRenderer
    tk.py           # TkRenderer (v0.7.x)
```

`plotter.py` depends on `evaluator.py` (already exists) and produces a `Scene`.
It has **no import of any renderer**. The CLI (`__main__.py`) instantiates the
correct renderer and calls `renderer.render(scene, output_path)`.

This is the boundary the spec requires: curve-generation logic lives entirely in
`plotter.py`; drawing logic lives entirely in `renderer/`. v0.7.x adds
`renderer/tk.py` with zero changes to `plotter.py`.

---

## Q6 — Discontinuity representation

Gaps are represented as **segment breaks**, not as explicit gap-marker objects.
A single continuous curve is one polyline (one element of `segments`). When the
evaluator returns a domain error for a sample, the running segment is closed and a
new one started after the gap. The renderers do not need to test for discontinuity;
they simply draw each segment independently.

This avoids special-casing in renderers and keeps the IR minimal.

---

## Q7 — Precedent applicability

| Model | Useful at our scale? |
|---|---|
| **matplotlib Figure/Axes** | Yes — direct inspiration. Axes = `Scene`; backend = `Renderer`. |
| **Cairo scene graph** | Overkill. Cairo's retained-mode graph is designed for complex compositing. A flat `segments` list is sufficient for a single-curve function plot. |

---

## Decision

**Use a single `Scene` dataclass (world-space coordinates, immutable, no renderer
knowledge) passed to a `Renderer` protocol.** PNG, SVG, and future Tk renderers all
implement the same interface. The plotter module produces scenes; the renderer module
consumes them. No fork or refactor is needed in v0.7.x.

### Struct fields confirmed

`width`, `height`, `x_min`, `x_max`, `y_min`, `y_max`, `x_ticks`, `y_ticks`,
`segments` (tuple of polylines in world coordinates).

### Renderer interface confirmed

`render(scene: Scene, output: Path) -> None` — raises `OSError` on write failure.

### Module boundary confirmed

`calc/plotter.py` → `Scene` → `calc/renderer/{png,svg,tk}.py`.
