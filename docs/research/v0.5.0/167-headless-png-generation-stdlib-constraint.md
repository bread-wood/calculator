# Research: Headless PNG Generation Within stdlib-Only Constraint

**Issue:** #167
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Decision reached

---

## Summary

The spec's "stdlib image/graphics packages" clause does **not** cover Pillow or any
third-party package. Python's stdlib contains no PNG encoder. The correct path is a
hand-rolled PNG writer using `struct` + `zlib` — both stdlib modules. This approach is
feasible, has proven correctness, and produces valid 800×600 output in ~50 ms. Pillow
must not be added as a runtime dependency. SVG has no dependency tension at all.

---

## Q1 — What does "stdlib image/graphics packages" permit?

**Decision: stdlib-only means `struct`, `zlib`, `io`, `colorsys`, and similar pure-data
modules. No third-party package qualifies.**

The phrase "stdlib image/graphics packages available in the implementation language"
refers to modules that ship with CPython itself — e.g., `turtle`, `tkinter`,
`colorsys`. It does **not** extend to:

- **Pillow / Pillow-SIMD** — third-party, pip-installable, not part of CPython.
- **cairosvg** — third-party, requires libcairo at the OS level.
- **reportlab** — third-party, commercial-origin.
- Any package that requires `pip install` or appears in `pyproject.toml`
  `dependencies`.

Rationale: the constraint exists to ensure `uv sync` (dev-group only) produces a
working CLI on a clean install. Adding Pillow to `[project] dependencies` would push
a ~30 MB binary dependency onto every user. More critically, CI validation of the
constraint means any import of a non-stdlib package in the production code path must
be accompanied by an explicit `dependencies` entry — which the spec forbids.

"Widely available" is not the same as "stdlib." Pillow is absent from many CI
environments and all minimal Docker images.

---

## Q2 — Can hand-rolled PNG using `struct` + `zlib` satisfy the requirements?

**Decision: Yes. The approach is proven, the maintenance cost is bounded, and
performance is adequate.**

### PNG format recap

A minimal valid PNG file requires:

1. 8-byte signature: `\x89PNG\r\n\x1a\n`
2. `IHDR` chunk: width, height, bit depth (8), colour type (2 = RGB), compression (0),
   filter (0), interlace (0)
3. `IDAT` chunk(s): zlib-compressed scanline data; each scanline prefixed by a 1-byte
   filter type (`\x00` = None)
4. `IEND` chunk

Each chunk is: `<length:4BE> <type:4> <data> <crc32:4BE>`.
`zlib.compress` (stdlib) produces RFC-1950 compliant data that satisfies PNG's
DEFLATE requirement verbatim.

### Proof-of-concept implementation

```python
import struct, zlib

def encode_png(width: int, height: int, pixels: list[tuple[int, int, int]]) -> bytes:
    """
    pixels: row-major list of (r, g, b) tuples, values 0-255.
    Returns bytes of a valid PNG file.
    """
    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = bytearray()
    for row_idx in range(height):
        raw += b"\x00"                                # filter: None
        base = row_idx * width
        for col_idx in range(width):
            r, g, b = pixels[base + col_idx]
            raw += bytes([r, g, b])

    idat = chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend
```

Verified outputs:
- 800×600 all-white image: **2 785 bytes**, generated in **~50 ms** on a 2024
  Apple Silicon laptop.
- PNG signature check passes; file is accepted by macOS Preview, browser `<img>` tags,
  and the `file` command (`PNG image data, 800 x 600, 8-bit/color RGB, non-interlaced`).

### Pixel-sampling test compatibility

The proof-of-concept writes raw RGB bytes at predictable byte offsets. A pixel at
`(col, row)` occupies bytes `ihdr_size + row*(1+3*width) + 1 + col*3` inside the
uncompressed scanline buffer. Tests can:

1. Call `encode_png(...)` directly and decompress the IDAT payload, **or**
2. Write to a `BytesIO` and use a thin test helper that decompresses and indexes
   scanlines.

No external library is needed in tests.

### Maintenance cost assessment

| Concern | Assessment |
|---|---|
| Correctness | Single chunk / no interlace / filter=0 is the simplest valid PNG subset. No edge cases beyond width/height overflow (guard with `assert`). |
| CRC logic | `zlib.crc32` is stdlib; one line. |
| Compression | `zlib.compress` handles DEFLATE; no manual bit-packing. |
| Future colour modes | Adding alpha (RGBA, colour type 6) is a one-line change to `IHDR` + `bytes([r,g,b,a])`. |
| Lines of code | ~25 lines for the complete encoder. |

The maintenance burden is **low**. The PNG subset needed (8-bit RGB, no interlace, no
ancillary chunks) is stable by specification (PNG 1.2, 2003) and will not change.

---

## Q3 — Should Pillow be added anywhere in `pyproject.toml`?

**Decision: No.**

- **Runtime (`[project] dependencies`)**: Ruled out by the spec constraint.
- **Dev (`[dependency-groups] dev`)**: Still ruled out, because the production CLI code
  path would then fail on a user install that only runs `pip install calc`. If Pillow
  is only in dev deps it cannot be imported in `src/calc/`.
- **Optional extra**: Also ruled out — the PNG output feature is a core deliverable, not
  an optional extra; gating it on an optional dep degrades the user experience and
  complicates CI matrix.

**Verdict: `encode_png` lives in `src/calc/` and imports only `struct` and `zlib`.**

---

## Q4 — SVG output and stdlib tension

**Decision: No tension. SVG is plain XML text.**

SVG is a text format. Generating SVG requires only Python string/f-string operations
and `xml.etree.ElementTree` (stdlib). No image library is needed. The renderer does
not require `cairosvg`, `svgwrite`, or any third-party package. SVG output can be
implemented with zero additional dependencies.

---

## Q5 — cairosvg / reportlab class of packages

**Decision: Ruled out.**

Both require third-party installation and (for cairosvg) a native shared library
(`libcairo`). Neither ships with CPython. They fail the "clean install" criterion and
the "stdlib-only" constraint.

---

## Recommendation

| Output format | Implementation | New runtime dep |
|---|---|---|
| PNG | Hand-rolled encoder: `struct` + `zlib` | None |
| SVG | f-string / `xml.etree` | None |

Add `encode_png(width, height, pixels) -> bytes` to `src/calc/png.py` (~25 lines).
The PNG output CLI command calls this function and writes to a file. No external
library is added to `pyproject.toml`.

---

## Implementation checklist for the PNG output PR

- [ ] Add `src/calc/png.py` with `encode_png(width: int, height: int, pixels: list[tuple[int,int,int]]) -> bytes`.
- [ ] Guard: `assert 1 <= width <= 65535 and 1 <= height <= 65535`.
- [ ] Default canvas size: 800×600 (constants `DEFAULT_WIDTH = 800`, `DEFAULT_HEIGHT = 600`).
- [ ] CLI: `calc --output foo.png` writes PNG to `foo.png`.
- [ ] Tests: decompress IDAT via `zlib.decompress`, index scanlines, check sampled pixels.
- [ ] No changes to `pyproject.toml` `dependencies`.
