# Research: Output Formatting for Function Results (Integer vs Decimal, Precision)

**Issue:** #44
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Complete

---

## Summary

The v0.1.x `format_result` function has one bug that will cause failures against the v0.2.0 acceptance tests: the decimal branch uses `f"{value:.15g}"` (15 significant digits), which truncates the last 1–2 digits required by the spec. The integer-detection logic is correct and handles all function results that are mathematically whole. The minimal fix is a one-line change: replace `f"{value:.15g}"` stripping with `repr(value)`.

---

## Findings

### 1. Integer-detection logic

Current implementation (`evaluator.py:38`):

```python
def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    s = f"{value:.15g}"
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s
```

`math.trunc(value) == value` correctly identifies whole-valued floats. Verified against all spec cases:

| Expression | Raw value | `trunc == value`? | Output |
|---|---|---|---|
| `sqrt(9)` | `3.0` | True | `"3"` ✓ |
| `pow(2, 10)` | `1024.0` | True | `"1024"` ✓ |
| `floor(2.7)` | `2` (int) | True | `"2"` ✓ |
| `ceil(2.3)` | `3` (int) | True | `"3"` ✓ |
| `sin(0)` | `0.0` | True | `"0"` ✓ |
| `cos(0)` | `1.0` | True | `"1"` ✓ |
| `log(1)` | `0.0` | True | `"0"` ✓ |
| `exp(0)` | `1.0` | True | `"1"` ✓ |
| `abs(-5.0)` | `5.0` | True | `"5"` ✓ |
| `sqrt(pow(3,2)+pow(4,2))` | `5.0` | True | `"5"` ✓ |

**Note:** `math.floor` and `math.ceil` return Python `int` in Python 3. `math.trunc(int_val) == int_val` evaluates to `True` (int comparison), so `str(int(value))` works correctly for these too.

**Note:** `pow(2, 10)` via `math.pow` returns `1024.0` (float). `math.trunc(1024.0) == 1024.0` → True. The integer path fires and outputs `"1024"` — no `"1024.0"` risk.

### 2. Decimal precision bug: `.15g` vs `repr`

The spec requires **full IEEE 754 double precision**, matching Python's `repr()` output (shortest round-trip string). The current formatter uses `f"{value:.15g}"` which gives at most 15 significant digits, then strips trailing zeros. This produces incorrect output for all spec-mandated decimal results:

| Expression | Expected (spec) | Current `.15g` output | `repr()` output |
|---|---|---|---|
| `sqrt(2)` | `1.4142135623730951` | `1.4142135623731` ✗ | `1.4142135623730951` ✓ |
| `atan2(1, 1)` | `0.7853981633974483` | `0.785398163397448` ✗ | `0.7853981633974483` ✓ |
| `pi` | `3.141592653589793` | `3.14159265358979` ✗ | `3.141592653589793` ✓ |
| `e` | `2.718281828459045` | `2.71828182845905` ✗ | `2.718281828459045` ✓ |
| `2 * pi` | `6.283185307179586` | `6.28318530717959` ✗ | `6.283185307179586` ✓ |

Python's `repr(float)` uses David Gay's dtoa algorithm to produce the **shortest decimal string that round-trips back to the same IEEE 754 double**. This matches the spec examples exactly.

### 3. Does `format_result` already handle function results?

Yes — `evaluate()` returns `float` for all node types, and `format_result` accepts `float`. Once functions are added to the evaluator, no routing change is needed; `format_result` is called once at the CLI layer for the final result.

### 4. `floor(2.7)` integer-detection edge case

`math.floor(2.7)` returns Python `int(2)`, not `float(2.0)`. `math.trunc(2) == 2` is `True`. `str(int(2))` → `"2"`. Works correctly with no special case needed.

### 5. Risk: `pow(2, 10)` formatted as `1024.0`

No risk. `math.pow(2, 10)` returns `1024.0` (float). `math.trunc(1024.0) == 1024.0` → `True`. The integer branch fires and returns `"1024"`.

---

## Acceptance Criteria Verification

| Criterion | Current formatter | After fix |
|---|---|---|
| `sqrt(9)` → `3` | ✓ | ✓ |
| `sqrt(2)` → `1.4142135623730951` | ✗ (`.15g` truncates) | ✓ |
| `atan2(1,1)` → `0.7853981633974483` | ✗ | ✓ |
| `pi` → `3.141592653589793` | ✗ | ✓ |
| `e` → `2.718281828459045` | ✗ | ✓ |
| `2 * pi` → `6.283185307179586` | ✗ | ✓ |
| `floor(2.7)` → `2` | ✓ | ✓ |
| `pow(2, 10)` → `1024` | ✓ | ✓ |

---

## Recommended Minimal Change

Replace the decimal branch in `format_result` with `repr(value)`:

```python
def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    return repr(value)
```

- `repr(float)` in CPython 3.1+ uses the shortest round-trip representation, guaranteed to match all spec examples.
- No trailing-zero stripping is needed — `repr` never emits unnecessary trailing zeros for non-whole floats.
- The integer check remains unchanged and covers all function results that are mathematically whole.
- Change scope: 3 lines removed, 1 line added in `evaluator.py`.

---

## Out of Scope

- `round(2.5)` → banker's rounding (Python 3 returns `2`, spec expects `3`). This is a separate behavior issue tracked by issue #41, not a formatting issue.
