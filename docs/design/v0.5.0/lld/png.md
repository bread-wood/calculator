# Low-Level Design — Module: `png`

**Milestone:** v0.5.0
**Issue:** #222
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

`src/calc/png.py` encodes an 8-bit RGB pixel buffer as a valid PNG file using only
`struct` and `zlib` from the Python standard library. It has no knowledge of the
rendering pipeline, coordinate transforms, or scene data — it operates purely at the
byte-encoding level.

---

## 2. File Location

```
src/calc/png.py
```

**Dependencies:** `struct` (stdlib), `zlib` (stdlib) — no other imports.

---

## 3. Public API

### 3.1 Constants

```python
DEFAULT_WIDTH: int = 800
DEFAULT_HEIGHT: int = 600
```

These are the canonical default canvas dimensions for the `plot` subcommand. They are
defined here (not in the CLI) so that tests can import them without importing
CLI-level modules. The CLI and `tests/test_png.py` both import from this module.

### 3.2 `encode_png`

```python
def encode_png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int]],
) -> bytes:
    ...
```

**Parameters:**

| Parameter | Type | Constraints |
|---|---|---|
| `width` | `int` | `1 ≤ width ≤ 65535` |
| `height` | `int` | `1 ≤ height ≤ 65535` |
| `pixels` | `list[tuple[int, int, int]]` | Row-major; `len(pixels) == width * height`; each channel in `[0, 255]` |

**Returns:** `bytes` — a complete, valid PNG file.

**Raises:** `AssertionError` if `width` or `height` is outside `[1, 65535]` (see §5).

---

## 4. Data Structures

### 4.1 Input pixel buffer

`pixels` is a flat row-major list of `(r, g, b)` integer tuples. Index for pixel at
column `c`, row `r`:

```
index = r * width + c
pixel = pixels[index]   # (R, G, B), each 0–255
```

No intermediate data structure is allocated beyond a `bytearray` for the raw
scanline buffer (see §6.2).

### 4.2 PNG chunk layout

Each PNG chunk has the structure:

```
[4 bytes] length   — big-endian uint32, length of `data` field only
[4 bytes] type tag — ASCII (e.g., b"IHDR", b"IDAT", b"IEND")
[N bytes] data     — chunk payload
[4 bytes] CRC-32   — over tag + data, big-endian uint32
```

The module builds three chunks: `IHDR`, `IDAT`, `IEND`.

### 4.3 IHDR payload layout

13 bytes, per PNG specification §11.2.2:

```
offset 0–3:  width        (big-endian uint32)
offset 4–7:  height       (big-endian uint32)
offset 8:    bit depth    = 8
offset 9:    colour type  = 2  (RGB truecolour)
offset 10:   compression  = 0  (DEFLATE)
offset 11:   filter       = 0  (adaptive filtering disabled)
offset 12:   interlace    = 0  (no interlace)
```

### 4.4 Raw scanline buffer

Before compression, the raw buffer is a `bytearray` of `height * (1 + 3 * width)`
bytes:

```
For each row r in 0..height-1:
  byte 0:         filter type = 0x00 (None)
  bytes 1..3*w:   R G B R G B … for each pixel in the row
```

Filter type `None` (0x00) means scanline bytes are written verbatim — no per-pixel
differencing. This maximises simplicity at the cost of some compression ratio, which
is acceptable for a development tool.

---

## 5. Key Algorithms

### 5.1 Chunk builder (inner function)

```python
def _chunk(tag: bytes, data: bytes) -> bytes:
    payload = tag + data
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)
```

- `tag` is always exactly 4 bytes (e.g., `b"IHDR"`).
- `zlib.crc32` computes CRC-32 over `tag + data` per PNG spec §5.
- Masking with `0xFFFFFFFF` ensures unsigned 32-bit representation on all platforms.
- The inner function avoids polluting module namespace; it is defined inside
  `encode_png` and is not exported.

### 5.2 IHDR chunk construction

```python
ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
ihdr = _chunk(b"IHDR", ihdr_data)
```

`struct.pack(">IIBBBBB", ...)` packs two uint32s (width, height) followed by five
uint8s (bit depth, colour type, compression, filter, interlace). Total: 13 bytes,
matching the PNG IHDR data length.

### 5.3 Raw scanline assembly

```python
raw = bytearray()
for row_idx in range(height):
    raw += b"\x00"                          # filter: None
    base = row_idx * width
    for col_idx in range(width):
        r, g, b = pixels[base + col_idx]
        raw += bytes([r, g, b])
```

Iteration is straightforward: outer loop over rows, inner loop over columns. A
`bytearray` is used to accumulate bytes efficiently via `+=`. The filter byte `\x00`
is prepended to each scanline.

**Alternative considered:** `bytearray` with pre-allocated size and `raw[offset] =
value` slice assignment — rejected as premature optimisation; the append approach is
clear and ~50 ms for 800×600, well within UX tolerance.

### 5.4 IDAT compression

```python
idat = _chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
```

- `zlib.compress` produces RFC-1950 compliant DEFLATE data, which is what PNG's IDAT
  requires verbatim (PNG uses DEFLATE/zlib, not raw DEFLATE).
- `level=6` is the zlib default and produces a good compression ratio without
  excessive CPU time. Choosing a fixed level (rather than relying on the platform
  default) ensures reproducible output sizes in testing, though byte-for-byte
  identity across platforms is not guaranteed (and not required — see §8.2).
- A single `IDAT` chunk is used. PNG allows multiple `IDAT` chunks; a single chunk
  is simpler, and `zlib.compress` returns a single buffer.

### 5.5 IEND chunk

```python
iend = _chunk(b"IEND", b"")
```

The IEND chunk has zero data bytes; its CRC covers only the tag `b"IEND"`.

### 5.6 Width/height guard

```python
assert 1 <= width <= 65535 and 1 <= height <= 65535
```

- `assert` is used rather than a custom error because this guard protects against
  internal programming errors (caller passes a nonsensical dimension), not user
  input. The CLI validates dimensions before calling `encode_png`.
- `65535` is the maximum dimension that fits in a 16-bit PNG dimension field without
  overflow. (PNG spec technically allows up to `2^31 − 1`, but values above `65535`
  are outside the scope of this tool's requirements and would produce multi-GB
  buffers.)

---

## 6. Complete Implementation

```python
import struct
import zlib

DEFAULT_WIDTH: int = 800
DEFAULT_HEIGHT: int = 600


def encode_png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int]],
) -> bytes:
    """Encode an 8-bit RGB pixel buffer as a PNG file.

    pixels: row-major list of (r, g, b) tuples, each channel 0-255.
    Returns a complete PNG file as bytes.
    """
    assert 1 <= width <= 65535 and 1 <= height <= 65535

    def _chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = bytearray()
    for row_idx in range(height):
        raw += b"\x00"
        base = row_idx * width
        for col_idx in range(width):
            r, g, b = pixels[base + col_idx]
            raw += bytes([r, g, b])

    idat = _chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend
```

Total: ~25 lines of implementation code.

---

## 7. Error Handling

| Condition | Detection point | Behaviour |
|---|---|---|
| `width` or `height` outside `[1, 65535]` | Top of `encode_png` | `AssertionError` (programming error; CLI validates before call) |
| `len(pixels) != width * height` | Not explicitly checked | `IndexError` from scanline loop (programming error) |
| Individual channel value outside `[0, 255]` | Not explicitly checked | `bytes([v])` raises `ValueError` for `v < 0` or `v > 255` (programming error) |
| `zlib.compress` failure | `zlib` module internals | `zlib.error` propagated unchanged (system-level; cannot recover) |

The module contains no `CalcError` subclasses. All errors from this module
are programming errors or system failures; user-facing errors are handled at the CLI
layer before `encode_png` is ever called.

---

## 8. Test Strategy

Tests live in `tests/test_png.py` (new file).

### 8.1 Unit tests for `encode_png`

| Test | Input | Assertion |
|---|---|---|
| `test_returns_bytes` | 1×1 white pixel | `isinstance(result, bytes)` |
| `test_png_signature` | 1×1 pixel | `result[:8] == b"\x89PNG\r\n\x1a\n"` |
| `test_ihdr_dimensions_1x1` | 1×1 white | IHDR bytes 16–23 decode to `(1, 1)` |
| `test_ihdr_dimensions_default` | 800×600 all-white | IHDR bytes 16–23 decode to `(800, 600)` |
| `test_ihdr_colour_type_is_rgb` | 1×1 pixel | `data[25] == 2` |
| `test_iend_present` | 1×1 pixel | Last 12 bytes contain `b"IEND"` chunk |
| `test_pixel_value_roundtrip` | 3×1, pixels: red/green/blue | Decompress IDAT; assert RGB bytes match input |
| `test_all_white_image` | 800×600 all-white | Decompress IDAT; first scanline filter byte is `0x00`; all RGB bytes are 255 |
| `test_all_black_image` | 800×600 all-black | Decompress IDAT; all RGB bytes are 0 |
| `test_assertion_width_zero` | `width=0` | `AssertionError` raised |
| `test_assertion_height_zero` | `height=0` | `AssertionError` raised |
| `test_default_constants` | — | `DEFAULT_WIDTH == 800`, `DEFAULT_HEIGHT == 600` |

### 8.2 PNG pixel sampling helper (for integration tests)

`tests/test_plot.py` uses the following stdlib-only helper to verify renderer pixel
placement (reproduced from research #171):

```python
import struct, zlib, pathlib

def read_png_pixel(path: pathlib.Path, col: int, row: int) -> tuple[int, int, int]:
    data = path.read_bytes()
    width, _ = struct.unpack(">II", data[16:24])
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
    stride = 1 + width * 3
    offset = row * stride + 1 + col * 3
    return raw[offset], raw[offset+1], raw[offset+2]
```

This helper is placed in `tests/test_plot.py` (or a shared `tests/helpers.py` if
reused), not in `src/calc/`. It works only with filter-type-0 scanlines (produced by
`encode_png`).

### 8.3 No golden-file tests

PNG byte output is not compared to stored reference files. `zlib` compression produces
platform-specific byte sequences; snapshot tests would produce false failures on CI.
Mathematical and structural assertions (§8.1, §8.2) are used exclusively.

### 8.4 Performance note

An 800×600 all-white PNG encodes in ~50 ms on a 2024 Apple Silicon laptop (measured
in research #167). No performance tests are required; the tool's UX is not sensitive
to encoding time at this scale.

---

## 9. Design Decisions and Rationale

| Decision | Choice | Rationale |
|---|---|---|
| Single IDAT chunk | One `zlib.compress` call → one `IDAT` | Simplest valid approach; no chunking logic needed |
| `zlib.compress(level=6)` | Fixed level | Reproducible output size; platform default can differ; level 6 is fast enough |
| Filter type `None` (0x00) | No per-scanline differencing | Simplest subset; adequate compression for plot images; avoids filter-selection logic |
| `assert` for dimension guard | Not a custom `CalcError` | Caller (CLI/renderer) is responsible for valid dimensions; this is an internal contract |
| Constants in `png.py` | `DEFAULT_WIDTH`, `DEFAULT_HEIGHT` | Single source of truth; CLI and tests both import from here |
| No `PLTE`, `gAMA`, `sRGB` chunks | Omitted | Not required by spec; minimises implementation; most image viewers use sRGB by default |
| No alpha channel | Colour type 2 (RGB), not 6 (RGBA) | Spec does not require transparency; adding alpha later is a one-line change |
| Inner function `_chunk` | Defined inside `encode_png` | Not part of public API; prevents namespace pollution; closure over nothing (pure function) |

---

## 10. Open Questions Resolved

From HLD §Open Questions, item 3:

> **`png` LLD** — Whether `encode_png` uses a single `IDAT` chunk or multiple; exact
> `zlib.compress` level used; whether width/height guard uses `assert` or raises a
> custom error.

Resolutions:
- **Single IDAT chunk.** A single `zlib.compress` call is simpler; multiple IDAT
  chunks are only needed for streaming large images, which is not a requirement here.
- **`level=6`.** Chosen explicitly to avoid platform-dependent defaults and ensure
  consistent behaviour in tests.
- **`assert` for width/height guard.** The CLI validates dimensions before calling
  `encode_png`; this guard is a programming-error check, not user-error handling.
