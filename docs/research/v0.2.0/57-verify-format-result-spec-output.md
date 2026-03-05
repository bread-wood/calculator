# Research: verify format_result produces spec-exact output strings for new values

**Issue:** #57
**Date:** 2026-03-04
**Status:** Complete

## Summary

The current `format_result` implementation uses `f"{value:.15g}"` with trailing-zero stripping. This produces only 15 significant digits, which is fewer than Python's `str()`/`repr()`, which use the shortest round-trip decimal representation (up to 17 significant digits). For all spec-mandated irrational values, `:.15g` produces strings that **do not match** the spec. Switching to `str(value)` (with the existing integer-check preserved) fixes all spec values without breaking any existing v0.1.x tests.

---

## Comparison Table

| Expression | Spec-mandated string | `str()` / `repr()` | `:.15g` (stripped) | `str()` matches spec | `:.15g` matches spec |
|---|---|---|---|---|---|
| `sqrt(2)` | `1.4142135623730951` | `1.4142135623730951` | `1.4142135623731` | ✓ | ✗ |
| `pi` | `3.141592653589793` | `3.141592653589793` | `3.14159265358979` | ✓ | ✗ |
| `e` | `2.718281828459045` | `2.718281828459045` | `2.71828182845905` | ✓ | ✗ |
| `atan2(1,1)` | `0.7853981633974483` | `0.7853981633974483` | `0.785398163397448` | ✓ | ✗ |
| `sqrt(9)` | `3` | `3` (via int check) | `3` | ✓ | ✓ |
| `sqrt(pow(3,2)+pow(4,2))` | `5` | `5` (via int check) | `5` | ✓ | ✓ |
| `pow(2,10)` | `1024` | `1024` (via int check) | `1024` | ✓ | ✓ |
| `2.5` (existing test) | `2.5` | `2.5` | `2.5` | ✓ | ✓ |
| `0.1` (existing test) | `0.1` | `0.1` | `0.1` | ✓ | ✓ |

> Note: `str(float)` and `repr(float)` produce identical output in Python 3.1+.

---

## Key Findings

### Q1: Does `f"{value:.15g}"` produce `1.4142135623730951` for `math.sqrt(2)`?

**No.** `:.15g` limits to 15 significant digits. After stripping trailing zeros, the result is `1.4142135623731` — which differs from the spec string `1.4142135623730951`. All four irrational spec values are affected.

### Q2: Should `format_result` use `str(value)` instead?

**Yes.** Python's `str(float)` (since Python 3.1) uses David Gay's algorithm to produce the shortest decimal string that round-trips back to the same IEEE 754 double. For `math.sqrt(2)`, this yields `1.4142135623730951`, exactly matching the spec. Since the spec strings were presumably taken from Python's default float representation, `str()` is the natural match.

### Q3: Are there spec values where `str()` and the spec string differ?

**No.** For every spec-mandated value tested (`sqrt(2)`, `pi`, `e`, `atan2(1,1)`, integer-valued results), `str(value)` exactly matches the spec string. Integer-valued floats like `sqrt(9) = 3.0` are already handled by the existing `math.trunc(value) == value` branch that returns `str(int(value))`.

### Q4: Does switching from `:.15g` to `str()` break existing v0.1.x tests?

**No.** All six existing `test_format_result` parametrized cases pass with `str(value)`:
- `5.0` → `"5"` (integer branch, unchanged)
- `2.5` → `"2.5"` ✓
- `2.0` → `"2"` (integer branch) ✓
- `-3.0` → `"-3"` (integer branch) ✓
- `0.0` → `"0"` (integer branch) ✓
- `0.1` → `"0.1"` ✓

---

## Recommended Implementation

Replace the `:.15g` branch in `format_result` with `str(value)`:

```python
# Current (broken for spec values)
def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    s = f"{value:.15g}"
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s

# Proposed (spec-correct)
def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    return str(value)
```

`str(value)` already produces the shortest round-trip representation without trailing zeros for values like `2.5` (gives `"2.5"`, not `"2.500000000000000"`), so no further stripping is needed.

---

## Recommendation

**Use `str(value)`** in the non-integer branch of `format_result`. It:
1. Produces spec-exact strings for all tested irrational values.
2. Does not break any existing v0.1.x tests.
3. Is simpler (no format string, no stripping loop).
4. Relies on Python's well-specified shortest-round-trip algorithm rather than an ad-hoc digit count.
