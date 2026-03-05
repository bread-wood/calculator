# Research: Headless Test Strategy for Image Correctness

**Issue:** #171
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Decision reached

---

## Summary

All image-correctness assertions can be made headlessly using Python stdlib alone —
no display, no Pillow, no pytest plugins beyond what is already installed. The
recommended strategy has three tiers: (1) dimension assertions via direct byte
inspection for PNG and XML attribute reads for SVG, (2) curve-content assertions via
`Scene` IR inspection (property-based, most robust) and PNG pixel sampling
(display-free, stdlib-only), and (3) SVG structural assertions via
`xml.etree.ElementTree`. Golden-file / snapshot tests are explicitly ruled out as
too fragile across platforms.

---

## Context

The v0.5.0 spec requires:

- `calc plot 'sin(x)' --width 800 --height 600` → 800×600 image.
- `calc plot 'sin(x)'` → curve crosses y=0 at x=0 (verified by pixel sampling).
- `make test` passes on macOS and Linux with **no display**.

The PNG renderer is hand-rolled using `struct` + `zlib` (see research #167). The
scene IR is a `Scene` dataclass with world-coordinate `segments` (see research
#166). The test suite uses `pytest` with no extra plugins; runtime dependencies are
stdlib-only.

---

## Tier 1 — Dimension Assertions

### PNG: read IHDR directly (no library)

A valid PNG file has a fixed-layout header:

```
bytes  0– 7   PNG signature (\x89PNG\r\n\x1a\n)
bytes  8–11   IHDR chunk length (always 0x0000000d = 13)
bytes 12–15   IHDR type ("IHDR")
bytes 16–19   image width  (big-endian uint32)
bytes 20–23   image height (big-endian uint32)
```

Width and height are at a fixed byte offset regardless of any other chunk content.

```python
import struct, pathlib

def read_png_dimensions(path: pathlib.Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height

def test_png_dimensions(tmp_path):
    out = tmp_path / "plot.png"
    subprocess.run(["calc", "plot", "sin(x)", "--width", "800", "--height", "600",
                    "--output", str(out)], check=True)
    assert read_png_dimensions(out) == (800, 600)
```

No external library. No display. Works on any POSIX platform.

### SVG: parse root element attributes

```python
import xml.etree.ElementTree as ET

def read_svg_dimensions(path: pathlib.Path) -> tuple[int, int]:
    root = ET.parse(str(path)).getroot()
    # Strip namespace prefix if present: {http://www.w3.org/2000/svg}svg
    w = root.get("width") or root.get("{http://www.w3.org/2000/svg}width")
    h = root.get("height") or root.get("{http://www.w3.org/2000/svg}height")
    return int(w), int(h)

def test_svg_dimensions(tmp_path):
    out = tmp_path / "plot.svg"
    subprocess.run(["calc", "plot", "sin(x)", "--width", "800", "--height", "600",
                    "--output", str(out)], check=True)
    assert read_svg_dimensions(out) == (800, 600)
```

`xml.etree.ElementTree` is stdlib; no dependency tension.

---

## Tier 2 — Curve-Content Assertions

Two approaches are recommended, ordered by robustness.

### Approach A — Scene IR inspection (preferred; display-free, no I/O)

The `Scene` dataclass (research #166) holds `segments` in **world coordinates**.
Mathematical invariants can be asserted directly on the `Scene`, bypassing the
renderer entirely. This is the most stable approach: it is independent of image
format, pixel coordinate transforms, anti-aliasing, and rendering rounding.

```python
from calc.plotter import build_scene   # produces Scene from expression + params

def test_sin_crosses_zero_at_origin():
    scene = build_scene("sin(x)", x_min=-10.0, x_max=10.0,
                        width=800, height=600)
    # Collect all (x, y) sample points across all segments
    points = [pt for seg in scene.segments for pt in seg]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    # sin(x) must cross y=0: some y values are positive, some negative
    assert any(y > 0 for y in ys), "sin(x) has no positive y samples"
    assert any(y < 0 for y in ys), "sin(x) has no negative y samples"

    # At x=0, sin(0)=0: the sample nearest x=0 must have |y| < epsilon
    nearest = min(points, key=lambda p: abs(p[0]))
    assert abs(nearest[1]) < 0.05, f"sin near x=0 is {nearest[1]!r}, expected ~0"

def test_sin_y_range_contains_expected_span():
    scene = build_scene("sin(x)", x_min=-10.0, x_max=10.0,
                        width=800, height=600)
    points = [pt for seg in scene.segments for pt in seg]
    ys = [p[1] for p in points]
    # sin(x) amplitude is 1; with 10% padding y range must span > 1.8
    assert max(ys) - min(ys) > 1.8

def test_tick_positions_within_axis_bounds():
    scene = build_scene("sin(x)", x_min=-10.0, x_max=10.0, width=800, height=600)
    for val, _ in scene.x_ticks:
        assert scene.x_min <= val <= scene.x_max
    for val, _ in scene.y_ticks:
        assert scene.y_min <= val <= scene.y_max
```

**Advantages:**
- No filesystem I/O, no subprocess, no pixel math.
- Cross-platform identical: world-coordinate invariants don't change between macOS
  and Linux.
- Resilient to rendering changes that don't break the math.
- Fast (unit-test speed, no image encoding).

**Limitation:** Does not verify the renderer itself. Renderer bugs (wrong coordinate
transform, off-by-one in scanline indexing) are invisible to Scene tests. Use Tier 1
+ Approach B to cover the renderer.

### Approach B — PNG pixel sampling (display-free; verifies renderer)

The hand-rolled PNG encoder (research #167) stores 8-bit RGB scanlines compressed
with `zlib`. Decompressing the IDAT chunk and indexing by scanline is possible with
stdlib alone.

#### Coordinate transform

The world→pixel transform the renderer uses (from the spec):

```
px = int((x_world - x_min) / (x_max - x_min) * width)   # column, 0-based
py = int((y_max - y_world) / (y_max - y_min) * height)   # row, 0-based (top=y_max)
```

For `sin(x)` with default domain `[-10, 10]` and auto y-range `[-1.1, 1.1]`:

- x=0, y=0 maps to pixel column `(0 - (-10)) / 20 * 800 = 400`, row `(1.1 - 0) / 2.2 * 600 = 300`.

The pixel at (col=400, row=300) should be **on or near the curve** and therefore
the curve color (typically dark/black or the configured line color), not the
background color (white).

#### PNG pixel sampling helper

```python
import struct, zlib, pathlib

def read_png_pixel(path: pathlib.Path, col: int, row: int) -> tuple[int, int, int]:
    """Return (R, G, B) of a single pixel in an 8-bit RGB PNG.

    Works only with filter-type-0 (None) scanlines produced by encode_png in
    calc/png.py. Raises ValueError for unsupported PNG variants.
    """
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    colour_type = data[25]
    if colour_type != 2:  # 2 = RGB
        raise ValueError(f"unsupported colour type {colour_type}")

    # Locate IDAT chunk (immediately after IHDR in our single-chunk encoder)
    # Walk chunks to find IDAT
    pos = 8
    idat_payload = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        tag = data[pos+4:pos+8]
        chunk_data = data[pos+8:pos+8+length]
        if tag == b"IDAT":
            idat_payload.extend(chunk_data)
        elif tag == b"IEND":
            break
        pos += 4 + 4 + length + 4

    raw = zlib.decompress(bytes(idat_payload))
    stride = 1 + width * 3  # filter byte + RGB bytes per scanline
    scanline_start = row * stride + 1  # skip filter byte
    offset = scanline_start + col * 3
    return raw[offset], raw[offset+1], raw[offset+2]
```

#### Test: sin(x) passes through y=0 at x=0

```python
def test_sin_origin_pixel_is_curve_color(tmp_path):
    """The pixel at the world origin (x=0, y=0) must be the curve color.

    Uses the known y-range for sin(x) with 10% padding: [-1.1, 1.1].
    """
    out = tmp_path / "plot.png"
    subprocess.run(
        ["calc", "plot", "sin(x)", "--width", "800", "--height", "600",
         "--output", str(out)],
        check=True,
    )
    # World-to-pixel transform (must match renderer implementation)
    x_min, x_max = -10.0, 10.0
    y_min, y_max = -1.1, 1.1   # after 10% auto-padding of sin's [-1, 1]
    col = int((0.0 - x_min) / (x_max - x_min) * 800)   # 400
    row = int((y_max - 0.0) / (y_max - y_min) * 600)   # 300

    # Check a ±2px neighbourhood to tolerate sub-pixel rounding
    BACKGROUND = (255, 255, 255)
    curve_found = False
    for dc in range(-2, 3):
        for dr in range(-2, 3):
            px = read_png_pixel(out, col + dc, row + dr)
            if px != BACKGROUND:
                curve_found = True
                break
    assert curve_found, "No curve pixel found near world origin (x=0, y=0)"
```

**Tolerance note:** Checking a 5×5 neighbourhood (±2 px) around the computed pixel
position absorbs sub-pixel rounding without making the test meaninglessly loose. The
curve is at most 1–2 px wide, so a 5×5 search will reliably hit it if the renderer
is correct.

**Known fragility:** The test depends on the exact y-range produced by the auto-pad
logic. If the implementation pads differently (e.g., 5% instead of 10%, or adds a
margin for tick labels), the expected `(col, row)` will be wrong. **Mitigation:**
expose the computed `y_min`/`y_max` from the Scene (already in the IR) and
parameterise the pixel test from the Scene's axis bounds rather than hard-coding
`[-1.1, 1.1]`.

```python
def test_sin_origin_pixel_is_curve_color_via_scene(tmp_path):
    scene = build_scene("sin(x)", x_min=-10.0, x_max=10.0, width=800, height=600)
    out = tmp_path / "plot.png"
    subprocess.run(
        ["calc", "plot", "sin(x)", "--width", "800", "--height", "600",
         "--output", str(out)],
        check=True,
    )
    # Derive pixel coords from the Scene the renderer will use
    col = int((0.0 - scene.x_min) / (scene.x_max - scene.x_min) * scene.width)
    row = int((scene.y_max - 0.0) / (scene.y_max - scene.y_min) * scene.height)
    BACKGROUND = (255, 255, 255)
    neighbours = [
        read_png_pixel(out, col + dc, row + dr)
        for dc in range(-2, 3) for dr in range(-2, 3)
    ]
    assert any(px != BACKGROUND for px in neighbours), \
        f"No curve pixel at origin neighbourhood (col={col}, row={row})"
```

This version never hard-codes `y_min`/`y_max`; it is stable against padding changes.

---

## Tier 3 — SVG Structural Assertions

SVG tests do not require any coordinate transform knowledge. Parse the XML and assert
on the geometric structure.

```python
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"

def test_svg_has_curve_polyline(tmp_path):
    out = tmp_path / "plot.svg"
    subprocess.run(["calc", "plot", "sin(x)", "--output", str(out)], check=True)
    root = ET.parse(str(out)).getroot()
    # Renderer must emit at least one <polyline> or <path> for the curve
    polylines = root.findall(f".//{{{NS}}}polyline") + root.findall(f".//{{{NS}}}path")
    assert len(polylines) >= 1, "SVG has no curve element"

def test_svg_curve_has_sufficient_points(tmp_path):
    out = tmp_path / "plot.svg"
    subprocess.run(["calc", "plot", "sin(x)", "--output", str(out)], check=True)
    root = ET.parse(str(out)).getroot()
    polylines = root.findall(f".//{{{NS}}}polyline")
    # At least one polyline must have ≥ 800 points (1 sample/pixel minimum)
    max_points = max(
        len(pl.get("points", "").split()) // 2  # "x,y x,y …"
        for pl in polylines
    ) if polylines else 0
    assert max_points >= 800, f"Largest polyline has only {max_points} points"

def test_svg_curve_y_values_span_expected_range(tmp_path):
    out = tmp_path / "plot.svg"
    subprocess.run(["calc", "plot", "sin(x)", "--output", str(out)], check=True)
    root = ET.parse(str(out)).getroot()
    polylines = root.findall(f".//{{{NS}}}polyline")
    assert polylines, "No polylines in SVG"
    ys = []
    for pl in polylines:
        pairs = pl.get("points", "").split()
        ys.extend(float(p.split(",")[1]) for p in pairs if "," in p)
    # SVG y-axis is inverted (0 = top). For sin(x), y values span the full height.
    # Check that the range of y pixel values is large (curve is not degenerate).
    assert max(ys) - min(ys) > 0.5 * 600, "SVG curve spans less than half the height"
```

SVG structural tests are **more stable than pixel tests** because they test geometry
without depending on colour palette, anti-aliasing, or exact coordinate rounding.
They also work on CI runners with no display and no image libraries.

---

## Ruled Out: Golden-File / Snapshot Tests

Golden-file tests store a reference image and diff new output against it. This
approach is **not recommended** for this project:

- PNG output differs by platform due to `zlib` compression level defaults and
  potential scanline ordering differences, producing false failures even when the
  image is visually identical.
- Regenerating golden files requires human review, adding maintenance overhead.
- The existing `make test` / `uv run pytest` setup has no image-diff infrastructure.
- The spec's cross-platform (macOS + Linux) requirement makes snapshot tests
  especially fragile.

**Decision: Do not add golden-file tests.**

---

## No Additional pytest Plugins Required

All three tiers use:

| Tool | Source |
|---|---|
| `struct` | Python stdlib |
| `zlib` | Python stdlib |
| `xml.etree.ElementTree` | Python stdlib |
| `subprocess` | Python stdlib |
| `pathlib` | Python stdlib |
| `pytest` | Already in `[dependency-groups] dev` |

No `pytest-image`, `pytest-snapshot`, `Pillow`, or any other additional package is
needed. The existing `uv run pytest tests/ -v` invocation requires no changes.

---

## Display Requirements

All three tiers run without a display:

- No `tkinter`, no `matplotlib.pyplot.show()`, no `Xvfb`, no `DISPLAY` env var.
- PNG and SVG are written to files and read back as bytes/XML.
- `build_scene` (Scene IR inspection) performs only arithmetic; it has no GUI import.
- `subprocess.run(["calc", "plot", ...])` invokes the CLI, which writes a file and
  exits. No window is opened.

`make test` on a headless CI runner (GitHub Actions ubuntu-latest, macOS-latest)
requires zero additional setup.

---

## Recommended Test Plan

### Dimension assertions (mandatory)

| Test | Method | What it checks |
|---|---|---|
| `test_png_default_dimensions` | Read IHDR bytes 16–23 | Default 800×600 |
| `test_png_custom_dimensions` | Read IHDR bytes 16–23 | `--width 400 --height 300` |
| `test_svg_dimensions` | ET root `width`/`height` attrs | SVG matches requested size |

### Curve-content assertions (mandatory)

| Test | Method | What it checks |
|---|---|---|
| `test_sin_y_range_sign_changes` | Scene IR | sin(x) has both pos and neg y samples |
| `test_sin_near_origin_y_near_zero` | Scene IR | sin(0) ≈ 0 in sample set |
| `test_sin_tick_bounds` | Scene IR | All ticks within axis bounds |
| `test_sin_segment_count_is_one` | Scene IR | Continuous curve = 1 segment |
| `test_sin_origin_pixel_is_curve_color` | PNG pixel sampling + Scene | Renderer places curve at correct pixel |
| `test_svg_has_curve_polyline` | SVG XML | At least one curve element |
| `test_svg_curve_has_sufficient_points` | SVG XML | ≥ 800 sample points |

### Discontinuity assertions (mandatory for gap criterion)

| Test | Method | What it checks |
|---|---|---|
| `test_reciprocal_has_gap` | Scene IR | `1/x` produces ≥ 2 segments |
| `test_reciprocal_no_crash` | subprocess exit code | Exit 0 for `1/x` on `[-2,2]` |

### Error-path assertions (already covered by existing test patterns)

Exit code + stderr: no image-inspection tools needed, same pattern as existing tests.

---

## Decision

**Use Scene IR inspection as the primary curve-content strategy. Add PNG pixel
sampling for one end-to-end renderer test. Use IHDR byte inspection for all PNG
dimension tests. Use `xml.etree.ElementTree` for SVG. No additional dependencies or
pytest plugins. No golden-file tests.**

This strategy is reliable (mathematical invariants don't flip between platforms),
maintainable (Scene tests survive renderer refactors), and fully display-free on
both macOS and Linux under `make test`.
