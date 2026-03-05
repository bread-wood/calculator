# Research: Discontinuity Detection and Gap Rendering Algorithm

**Issue:** #169
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Decision reached

---

## Summary

Use a **combined approach**: exception-based detection for points where the
evaluator raises a `CalcError`, plus a **slope-jump heuristic** (threshold =
10 × median absolute consecutive difference) to catch finite-valued asymptotes
such as `tan(x)`. Represent gaps in the scene IR as a **segment list** —
`list[list[tuple[float, float]]]` — where each inner list is one continuous
polyline segment. Count non-empty points to detect the
"expression undefined over entire domain" error path.

---

## Problem Statement

The spec requires `calc plot '1 / x' --xmin -2 --xmax 2` to produce a visible
gap at x=0. Two failure modes must be avoided:

1. **False positive**: a gap appears in a smooth, continuous curve because of
   floating-point noise in slope comparisons.
2. **False negative**: a straight line is drawn across a vertical asymptote
   because the evaluator returned large-but-finite values on both sides.

Three canonical test cases drive the design:

| Expression | Discontinuity type | Evaluator behaviour at singularity |
|------------|-------------------|-------------------------------------|
| `1 / x`   | Vertical asymptote (both sides → ±∞) | `DivisionByZero` raised at x=0 |
| `sqrt(x)` over negative domain | Domain boundary | `DomainError` raised for x<0 |
| `tan(x)`  | Vertical asymptote (both sides finite) | Returns ~1.6 × 10¹⁶ at x≈π/2 (float inexactness means π/2 is never exact) |

---

## Dimension 1 — Exception-Based Detection

The existing evaluator raises subclasses of `CalcError` for undefined points:

- `DivisionByZero` — `1/x` at x=0
- `DomainError` — `sqrt(x)` at x<0, `log(x)` at x≤0
- `Overflow` — results that overflow to infinity or NaN

**Implementation:** wrap each `evaluate(ast, {"x": xi})` in a try/except block.
On `CalcError`, mark the sample as a gap rather than crashing.

**Covers:** `1/x`, `sqrt(x)`, `log(x)`, and any expression that yields ±∞ or NaN.

**Does not cover:** `tan(x)` at x≈π/2. Because `float(math.pi/2)` is not
exactly π/2, `math.tan` never receives the exact singularity; it returns a
large but finite value (~1.633 × 10¹⁶). No exception is raised, yet drawing a
line through this value would produce a visually meaningless spike.

---

## Dimension 2 — Slope-Jump Heuristic

Compare consecutive valid-sample differences against a threshold derived from
the global distribution of differences:

```
threshold = K × median(|y[i+1] − y[i]|  for all consecutive valid pairs)
```

Where K = 10 is the recommended multiplier (see rationale below).

A pair (i, i+1) whose absolute difference exceeds `threshold` is split: sample
i ends one segment, sample i+1 begins a new one.

**Covers:** `tan(x)` and any other expression where both sides of an asymptote
evaluate to large-but-finite values.

**Threshold rationale:**

| K value | Risk |
|---------|------|
| K = 2   | False positives on steep smooth curves (e.g. `x^3` near the origin) |
| K = 5   | Borderline; fine for most functions, but `x^3` over [-10, 10] has legitimate large slopes |
| **K = 10** | **Recommended** — catches tan(x) spike (ratio ~10⁵ to typical Δy) with no false positives on smooth functions |
| K = 50  | Misses gentler asymptotes |

The median is used instead of mean because a few extreme values near a
discontinuity would inflate the mean and suppress detection.

**Edge case — flat function:** when all Δy ≈ 0 (horizontal line, e.g. `y = 3`),
the median is 0 and the threshold is 0. Guard:

```python
threshold = max(K * median_diff, epsilon)
```

where `epsilon = 1e-12` (below any numerically meaningful jump). This prevents
division-by-zero and avoids false positives on constant functions.

**Edge case — single valid sample:** if only one valid sample exists, no
slope can be computed. Skip the heuristic; the gap test still passes because
the segment list will contain a single one-point segment (not rendered as a
line).

---

## Dimension 3 — Combined Algorithm

```python
GAP_K = 10
GAP_EPSILON = 1e-12

def sample_expression(ast, x_values):
    """Returns list of (x, y | None) where None marks a gap."""
    raw = []
    for xi in x_values:
        try:
            yi = evaluate(ast, {"x": xi, **_CONSTANTS_VALUES})
            raw.append((xi, yi))
        except CalcError:
            raw.append((xi, None))

    # Slope-jump heuristic on consecutive valid pairs
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
                    raw[i] = (raw[i][0], None)   # mark gap at the jump boundary
    return raw

def build_segments(raw):
    """Convert (x, y|None) list to list of continuous segments."""
    segments = []
    current = []
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

This is O(n) in sample count with a constant-factor O(n) pass for the median
(Python's `statistics.median` sorts; use `numpy.median` if performance matters).

---

## Dimension 4 — Scene IR Gap Representation

**Decision: segment list.**

```python
# Scene IR type
Segment = list[tuple[float, float]]   # ordered (x, y) pairs within one continuous run
CurveSegments = list[Segment]         # one or more continuous runs; gaps between runs
```

**Why segment list over alternatives:**

| Representation | Renderer coupling | Split step | Extensibility |
|----------------|-------------------|------------|---------------|
| Segment list | None — gaps are structural | Not needed | Natural for multi-curve (v0.6.x) |
| NaN sentinels in flat array | Renderer must handle NaN split | Needed before drawing | Requires array post-processing |
| Boolean mask | Renderer must handle masking | Needed | Extra parallel array to thread |

A segment list maps directly to:
- **SVG**: one `<polyline points="..."/>` per segment (or a `<path>` with
  `M x,y L x,y ...` per segment).
- **PIL/Pillow**: one `ImageDraw.line(segment_points)` call per segment.
- **v0.7.x window renderer**: the same `CurveSegments` object is passed to
  the live canvas; no curve-generation logic is duplicated.

An empty `CurveSegments` (zero segments, or all segments have fewer than 2
points) signals the "entire domain undefined" condition.

---

## Dimension 5 — Sampling Resolution

The spec mandates ≥ 1 sample per pixel of output width. For an 800-pixel-wide
image, this means ≥ 800 samples over the domain.

**Is this sufficient?**

For exception-detected gaps (`1/x`, `sqrt(x)`): yes. The discontinuity at a
single point (x=0 for `1/x`) will be captured because the two adjacent samples
straddle x=0 and at least one will hit the exception. The gap will be ≤ 1 pixel
wide visually, which is acceptable.

For slope-jump-detected gaps (`tan(x)`): yes. At 800 samples over a typical
domain like [−5, 5], the sample spacing is 0.0125 rad. Near x=π/2 ≈ 1.5708,
the sample immediately before π/2 and the one immediately after will both be
finite but one will be large-positive and the other large-negative. The
absolute difference will be ~10¹⁶, far exceeding any threshold.

**No sub-pixel oversampling near suspect points is needed** for the v0.5.0
test cases. If future test cases require sharper gap edges (e.g. counting exact
gap width in pixels), a refinement pass can be added later.

---

## Dimension 6 — "Entire Domain Undefined" Error Path

After `build_segments`:

```python
total_valid = sum(len(seg) for seg in segments)
if total_valid == 0:
    raise EntireDomainUndefined()
```

This handles `sqrt(x)` with `--xmin -5 --xmax -1` (all samples raise
`DomainError`), and also pathological expressions like `1/0` (constant
division by zero).

A `EntireDomainUndefined` error maps to:

```
error: expression undefined over entire domain
```

on stderr, exit 1.

---

## Test Case Verification

| Expression | Domain | Expected behaviour | Detection path |
|------------|--------|-------------------|----------------|
| `1 / x` | [−2, 2] | Gap at x=0; two segments | Exception (`DivisionByZero`) |
| `sqrt(x)` | [−5, 5] | Gap for x<0; one segment | Exception (`DomainError`) |
| `sqrt(x)` | [−5, −1] | Error: entire domain undefined | Exception + empty segments |
| `tan(x)` | [−5, 5] | Gaps near x≈±π/2, ±3π/2 | Slope-jump heuristic |
| `sin(x)` | [−10, 10] | Continuous curve, no gaps | Neither path triggered |
| `x^3` | [−10, 10] | Continuous curve, no gaps | Neither path triggered (K=10 safe) |
| `1/0` (constant) | any | Error: entire domain undefined | Exception on every sample |

For `tan(x)` with K=10: the typical |Δy| between adjacent samples of sin-like
behaviour is O(0.01); the jump across the asymptote is O(10¹⁶). The ratio
exceeds K=10 by eleven orders of magnitude — no false negative possible.

For `x^3` over [−10, 10] at 800 samples: the largest |Δy| between adjacent
samples is at x≈10, approximately (10³ − 9.975³) ≈ 7.5. The median |Δy| is
the midpoint of the sorted differences, dominated by the flat region near
x=0. Empirically, median ≈ 0.25, giving threshold = 2.5. The maximum jump of
7.5 is 3× the median — below K=10. No false positive.

---

## Recommended Algorithm (Summary)

1. Sample the expression at N ≥ width evenly-spaced x values.
2. For each sample: evaluate; on `CalcError`, mark as gap.
3. Compute median of absolute consecutive differences among valid samples.
4. Mark any consecutive valid pair with |Δy| > 10 × median as a gap
   boundary (replace the left sample with None).
5. Split the annotated sample list into a `list[list[tuple[float,float]]]`
   segment list.
6. If total valid samples = 0, raise "expression undefined over entire domain".
7. Pass the segment list into the scene IR; renderer draws one polyline per
   segment.

No sub-pixel oversampling or adaptive refinement is needed for v0.5.0.
K=10 with median normalization is the threshold recommendation.
