# Low-Level Design — Module: `plotter`

**Milestone:** v0.5.0
**Module:** `plotter` (`src/calc/plotter.py`)
**Issue:** #223
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

`plotter.py` owns all curve-generation and axis mathematics for the `calc plot` command. It:

1. Samples an expression AST over a uniform x-grid.
2. Detects discontinuities (exception-based + slope-jump heuristic).
3. Splits the sample list into continuous polyline segments.
4. Computes the padded y-range.
5. Computes tick positions and labels for both axes.
6. Returns an immutable `Scene` dataclass consumed by the renderer layer.

`plotter.py` has **no import of any renderer**. It imports only `evaluator`, `errors`, `statistics`, and `math`.

---

## 2. Data Structures

### 2.1 `Scene` (frozen dataclass)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Scene:
    width:    int
    height:   int
    x_min:    float
    x_max:    float
    y_min:    float   # padded (after 10% margin applied)
    y_max:    float   # padded (after 10% margin applied)
    x_ticks:  tuple[tuple[float, str], ...]
    y_ticks:  tuple[tuple[float, str], ...]
    segments: tuple[tuple[tuple[float, float], ...], ...]
```

All fields are immutable types (`int`, `float`, nested `tuple`). `frozen=True` makes `Scene` hashable and thread-safe, supporting the planned v0.7.x Tk renderer.

**Field semantics:**

| Field | Type | Description |
|---|---|---|
| `width`, `height` | `int` | Canvas dimensions in pixels |
| `x_min`, `x_max` | `float` | User-supplied domain bounds (not padded) |
| `y_min`, `y_max` | `float` | Auto-computed y bounds with 10% padding |
| `x_ticks` | `tuple[tuple[float, str], ...]` | `(world_value, label)` pairs for x-axis |
| `y_ticks` | `tuple[tuple[float, str], ...]` | `(world_value, label)` pairs for y-axis |
| `segments` | `tuple[tuple[tuple[float, float], ...], ...]` | Outer: list of continuous runs; inner: `(x, y)` world-coordinate pairs |

**Working types inside `build_scene` (converted to tuples before returning):**

```python
RawSample  = tuple[float, float | None]   # (x, y) or (x, None) for a gap
Segment    = list[tuple[float, float]]    # mutable during construction
SegmentList = list[Segment]
```

### 2.2 Module-level constants

```python
GAP_K       = 10       # slope-jump multiplier
GAP_EPSILON = 1e-12    # floor for threshold when curve is flat
_TICK_TARGET_N = 6     # default tick count for Heckbert algorithm
```

---

## 3. Public API

### 3.1 `build_scene`

```python
def build_scene(
    ast: ASTNode,
    x_min: float,
    x_max: float,
    width: int,
    height: int,
) -> Scene:
```

**Pre-conditions (caller-enforced):**
- `x_min < x_max` (validated by CLI before calling)
- `width >= 1`, `height >= 1`

**Post-conditions:**
- Returns a valid `Scene` with `len(segments) >= 1` and at least one segment with at least one point.
- Raises `DomainEmpty` if every sample failed evaluation.

**Algorithm (see §4 for detail):**

1. Generate `x_values` using linspace with `n = width` samples.
2. Call `_sample_expression(ast, x_values)` → `list[RawSample]`.
3. Apply slope-jump heuristic to mark additional gaps.
4. Call `_build_segments(raw)` → `SegmentList`.
5. Count total valid points; raise `DomainEmpty` if zero.
6. Collect all valid y-values; compute padded y-range.
7. Call `_calc_ticks(x_min, x_max)` and `_calc_ticks(y_min_padded, y_max_padded)`.
8. Convert `SegmentList` to nested tuples; return `Scene`.

---

## 4. Key Algorithms

### 4.1 Linspace

```python
def _linspace(start: float, stop: float, n: int) -> list[float]:
    if n == 1:
        return [start]
    return [start + i * (stop - start) / (n - 1) for i in range(n)]
```

Multiply-based (not iterative addition) to prevent floating-point accumulation. `n = width` ensures the spec constraint of ≥ 1 sample per output pixel.

### 4.2 `_sample_expression`

```python
def _sample_expression(
    ast: ASTNode,
    x_values: list[float],
) -> list[RawSample]:
```

For each `xi` in `x_values`:
- Call `evaluate(ast, {"x": xi, **_CONSTANTS_VALUES})`.
- On success: append `(xi, yi)`.
- On `CalcError`: append `(xi, None)` — marks a gap.

This catches `DivisionByZero`, `DomainError`, and `Overflow` per sample.

### 4.3 Slope-jump heuristic

Runs on the output of `_sample_expression` before segment construction:

```python
diffs = [
    abs(raw[i+1][1] - raw[i][1])
    for i in range(len(raw) - 1)
    if raw[i][1] is not None and raw[i+1][1] is not None
]
if diffs:
    median_diff = statistics.median(diffs)
    threshold = max(GAP_K * median_diff, GAP_EPSILON)
    for i in range(len(raw) - 1):
        if raw[i][1] is not None and raw[i+1][1] is not None:
            if abs(raw[i+1][1] - raw[i][1]) > threshold:
                raw[i] = (raw[i][0], None)  # mark left boundary as gap
```

- `GAP_K = 10` catches `tan(x)` asymptotes (ratio ~10¹¹) without false positives on smooth curves like `x^3` (ratio ~3×).
- `GAP_EPSILON = 1e-12` prevents threshold of zero on flat functions.
- Uses `statistics.median` (stdlib) — O(n log n) due to sorting.
- If `diffs` is empty (zero or one valid sample), the heuristic is skipped entirely.

### 4.4 `_build_segments`

```python
def _build_segments(raw: list[RawSample]) -> SegmentList:
    segments: SegmentList = []
    current: list[tuple[float, float]] = []
    for x, y in raw:
        if y is None:
            if current:
                segments.append(current)
                current = []
        else:
            current.append((x, y))
    if current:
        segments.append(current)
    return segments
```

O(n). Renderers draw each segment independently — no gap-marker handling needed in renderer code.

### 4.5 Y-range computation with padding

```python
y_valid = [y for seg in segments for x, y in seg]
y_raw_min = min(y_valid)
y_raw_max = max(y_valid)

if y_raw_min == y_raw_max:
    # Constant function: defer padding to calc_ticks special case
    y_min_padded = y_raw_min
    y_max_padded = y_raw_max
else:
    span = y_raw_max - y_raw_min
    y_min_padded = y_raw_min - 0.1 * span
    y_max_padded = y_raw_max + 0.1 * span
```

When `y_min == y_max` (constant function, e.g. `y = 3`), the padding is left to `_calc_ticks` which has a dedicated constant-value branch (see §4.6). The `Scene` stores the raw equal values; the tick algorithm expands the visible range.

### 4.6 `_calc_ticks` (Heckbert nice-numbers, 1990)

```python
def _calc_ticks(
    data_min: float,
    data_max: float,
    target_n: int = _TICK_TARGET_N,
) -> list[tuple[float, str]]:
```

Returns a list of `(world_value, label)` pairs where `label = f"{world_value:.3g}"`.

**Degenerate case (`data_min == data_max`):**

```python
v = data_min
if v == 0.0:
    raw_ticks = [-1.0, 0.0, 1.0]
else:
    step = _nice_num(abs(v) * 0.1, round_=True)
    raw_ticks = [v - step, v, v + step]
```

**Normal case:**

```python
def _nice_num(x: float, round_: bool) -> float:
    exp = math.floor(math.log10(abs(x))) if x != 0 else 0
    f = x / (10 ** exp)
    if round_:
        nf = 1 if f < 1.5 else (2 if f < 3 else (5 if f < 7 else 10))
    else:
        nf = 1 if f <= 1 else (2 if f <= 2 else (5 if f <= 5 else 10))
    return nf * (10 ** exp)

data_range = data_max - data_min
interval = _nice_num(data_range / (target_n - 1), round_=True)
tick_min = math.floor(data_min / interval) * interval
tick_max = math.ceil(data_max / interval) * interval
n_steps = round((tick_max - tick_min) / interval) + 1
raw_ticks = [
    tick_min + i * interval
    for i in range(n_steps)
    if (tick_min + i * interval) >= data_min - 1e-10 * data_range
    and (tick_min + i * interval) <= data_max + 1e-10 * data_range
]
if len(raw_ticks) < 2:
    raw_ticks = [tick_min, tick_max]
```

Tick positions are computed by multiplication (`tick_min + i * interval`), not iterative addition, to avoid accumulation error.

Label format: `f"{v:.3g}"` — strips trailing zeros, switches to scientific notation for very large or very small values automatically.

**Verified examples:**

| Call | Result positions |
|---|---|
| `_calc_ticks(0, 10)` | `[0, 2, 4, 6, 8, 10]` |
| `_calc_ticks(-10, -2)` | `[-10, -8, -6, -4, -2]` |
| `_calc_ticks(-3.1, 7.4)` | `[-4, -2, 0, 2, 4, 6, 8]` |
| `_calc_ticks(0, 0)` | `[-1.0, 0.0, 1.0]` |
| `_calc_ticks(5, 5)` | `[4.5, 5.0, 5.5]` |
| `_calc_ticks(-0.001, 0.001)` | `[-0.001, 0, 0.001]` |

---

## 5. Complete `build_scene` Flow

```
build_scene(ast, x_min, x_max, width, height)
│
├─ x_values = _linspace(x_min, x_max, n=width)
│
├─ raw = _sample_expression(ast, x_values)
│       └─ for each xi: evaluate(ast, {"x": xi, **_CONSTANTS_VALUES})
│              CalcError → (xi, None)
│
├─ [slope-jump heuristic in-place on raw]
│       diffs = |Δy| for consecutive valid pairs
│       threshold = max(10 × median(diffs), 1e-12)
│       mark raw[i] = (xi, None) when |Δy| > threshold
│
├─ segments = _build_segments(raw)
│
├─ if sum(len(s) for s in segments) == 0:
│       raise DomainEmpty
│
├─ y_valid = [y for seg in segments for _, y in seg]
│   y_raw_min, y_raw_max = min(y_valid), max(y_valid)
│   if y_raw_min == y_raw_max:
│       y_min_padded, y_max_padded = y_raw_min, y_raw_max
│   else:
│       span = y_raw_max - y_raw_min
│       y_min_padded = y_raw_min - 0.1 * span
│       y_max_padded = y_raw_max + 0.1 * span
│
├─ x_ticks = _calc_ticks(x_min, x_max)
│   y_ticks = _calc_ticks(y_min_padded, y_max_padded)
│
└─ return Scene(
       width=width, height=height,
       x_min=x_min, x_max=x_max,
       y_min=y_min_padded, y_max=y_max_padded,
       x_ticks=tuple((v, f"{v:.3g}") for v in x_ticks),
       y_ticks=tuple((v, f"{v:.3g}") for v in y_ticks),
       segments=tuple(tuple(seg) for seg in segments),
   )
```

---

## 6. Error Handling

| Condition | Raised by | Error class | Description |
|---|---|---|---|
| Every sample raises `CalcError` | `build_scene` (post-segment) | `DomainEmpty` | `"expression undefined over entire domain"` |
| Individual sample fails | `_sample_expression` | — | Marked as gap `(xi, None)`; not propagated |

`build_scene` itself raises only `DomainEmpty`. All other `CalcError` subclasses from `evaluate` are caught per-sample and turned into gaps.

The caller (`run_plot` in `__main__.py`) is responsible for catching `DomainEmpty` and routing it to stderr + exit 1 via `error_message()`.

---

## 7. Module Interface Summary

```python
# Public
def build_scene(
    ast: ASTNode,
    x_min: float,
    x_max: float,
    width: int,
    height: int,
) -> Scene: ...

@dataclass(frozen=True)
class Scene: ...

# Internal (not imported by renderers or CLI)
def _linspace(start: float, stop: float, n: int) -> list[float]: ...
def _sample_expression(ast: ASTNode, x_values: list[float]) -> list[RawSample]: ...
def _build_segments(raw: list[RawSample]) -> SegmentList: ...
def _calc_ticks(data_min: float, data_max: float, target_n: int = 6) -> list[tuple[float, str]]: ...
def _nice_num(x: float, round_: bool) -> float: ...
```

Only `build_scene` and `Scene` are part of the module's public contract.

---

## 8. Dependencies

| Import | Source | Usage |
|---|---|---|
| `evaluate` | `calc.evaluator` | Evaluate AST at each x sample |
| `_CONSTANTS_VALUES` | `calc.evaluator` | Provide `{"pi": ..., "e": ...}` to each sample |
| `CalcError` | `calc.errors` | Catch per-sample evaluation failures |
| `DomainEmpty` | `calc.errors` | Raise when entire domain is undefined |
| `statistics` | stdlib | `statistics.median` for slope-jump threshold |
| `math` | stdlib | `math.floor`, `math.ceil`, `math.log10` in `_nice_num` |

No renderer imports. No `pathlib`, `struct`, or `zlib`.

---

## 9. Test Strategy

Tests live in `tests/test_plotter.py` (new file).

### 9.1 Scene IR inspection (primary)

All tests call `build_scene(ast, ...)` directly and assert invariants on the returned `Scene`. No rendering, no pixel decoding, no file I/O.

**Basic curve tests:**

| Test | Expression | Domain | Assertion |
|---|---|---|---|
| Continuous curve | `sin(x)` | `[-10, 10]` | `len(scene.segments) == 1`; segment length ≥ `width` |
| Positive-only domain | `sqrt(x)` | `[0, 10]` | `len(scene.segments) == 1`; all y ≥ 0 |
| Boundary gap | `sqrt(x)` | `[-5, 5]` | `len(scene.segments) == 1`; first segment starts at x ≥ 0 |
| Asymptote gap | `1 / x` | `[-2, 2]` | `len(scene.segments) == 2`; segments on opposite sides of x=0 |
| Slope-jump gap | `tan(x)` | `[-5, 5]` | `len(scene.segments) >= 3` (gaps near ±π/2) |
| Smooth steep | `x^3` | `[-10, 10]` | `len(scene.segments) == 1` (no false positive with K=10) |

**DomainEmpty:**

| Test | Expression | Domain | Expected |
|---|---|---|---|
| All-negative domain | `sqrt(x)` | `[-5, -1]` | `raises DomainEmpty` |
| Constant zero-division | `1/0` | any | `raises DomainEmpty` |

**Y-range and padding:**

| Test | Assertion |
|---|---|
| `sin(x)` | `scene.y_min < -1` and `scene.y_max > 1` (10% padding beyond [-1,1]) |
| `sin(x)` | `scene.y_min ≈ -1.2` and `scene.y_max ≈ 1.2` (±10% of span=2) |
| Constant `y=3` | `scene.y_min == scene.y_max == 3.0` (passed to tick algo as-is) |

**Tick assertions:**

| Test | Assertion |
|---|---|
| x-ticks for `[0, 10]` | positions include `0.0` and `10.0`; all within `[0, 10]` |
| x-ticks for `[-3.1, 7.4]` | at least one tick ≤ 0 and at least one tick ≥ 0 (straddles zero) |
| tick labels | each label string parses as a valid float; `{:.3g}` format verified |
| constant y | y_ticks has at least 3 entries; middle entry equals constant value |

**Scene field types:**

- `scene.segments` is `tuple` (not `list`); each segment is `tuple`; each point is `tuple[float, float]`.
- `scene.x_ticks` and `scene.y_ticks` are `tuple[tuple[float, str], ...]`.

### 9.2 Unit tests for internal helpers

| Helper | Test cases |
|---|---|
| `_linspace(0, 1, 5)` | Returns `[0, 0.25, 0.5, 0.75, 1.0]` exactly |
| `_linspace(a, b, 1)` | Returns `[a]` |
| `_nice_num(3.5, True)` | Returns `5.0` |
| `_nice_num(3.5, False)` | Returns `5.0` |
| `_calc_ticks(0, 10)` | Positions `[0, 2, 4, 6, 8, 10]` |
| `_calc_ticks(0, 0)` | Returns 3 ticks; middle is `0.0` |
| `_calc_ticks(5, 5)` | Returns 3 ticks; middle is `5.0`; step is `0.5` |
| `_build_segments([...])` | Gap at `None`; segments split correctly |

### 9.3 Integration with evaluator

- Parse `sin(x)` → `build_scene` → assert non-empty segments.
- Parse `x + undefined_var` → assert `DomainEmpty` (all samples fail with `UndefinedVariable`).

### 9.4 What is NOT tested here

- PNG/SVG pixel content — tested in `tests/test_renderer.py` and `tests/test_plot.py`.
- CLI argument parsing — tested in `tests/test_plot.py`.
- `encode_png` — tested in `tests/test_png.py`.

---

## 10. Open Questions Resolved

This LLD resolves the plotter-related open questions from the HLD:

| HLD Open Question | Decision |
|---|---|
| `linspace` implementation | `[x_min + i*(x_max-x_min)/(n-1) for i in range(n)]` — multiply-based, no `statistics`/`math` helper needed |
| Segments as `list[list]` vs `tuple[tuple]` during construction | Working type is `list[list[tuple]]`; converted to `tuple[tuple[tuple]]` at `Scene` construction boundary |
| `y_min == y_max` handling (constant function) | Store equal values in `Scene`; `_calc_ticks` degenerate branch expands tick range around the constant |
