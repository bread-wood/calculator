# Research: Domain Error Detection Strategy (sqrt(-1), log(0))

**Issue:** #74
**Milestone:** v0.2.0
**Date:** 2026-03-04

---

## 1. Implementation Language

The project is implemented in **Python** (CPython ≥ 3.12). The build system is
`hatchling`; the runtime stdlib is used exclusively — no C extensions beyond
CPython's built-in `math` module.

This eliminates the C/C++ concerns about `errno`, `MATH_ERRNO`, and
`math_errhandling` entirely. Python's `math` module is a thin wrapper around the
platform `libm`, but Python normalises all error signalling: domain errors raise
`ValueError`, overflow errors raise `OverflowError`. These exceptions are
consistent across CPython on macOS (Apple libm) and Linux (glibc), regardless of
how the underlying C library sets `errno`.

---

## 2. Empirical Verification (macOS, CPython 3.12)

Tested locally on macOS (Darwin 23.5.0, CPython 3.12):

| Expression | Result |
|------------|--------|
| `math.sqrt(-1)` | `ValueError: math domain error` |
| `math.log(0)` | `ValueError: math domain error` |
| `math.tan(math.pi / 2)` | `1.633123935319537e+16` (large finite float, not inf) |
| `math.exp(1000)` | `OverflowError: math range error` |

The same behaviour is documented for Linux (glibc). Python normalises `libm`
domain errors to `ValueError` on both platforms. There are no platform-specific
differences relevant to this detection strategy.

---

## 3. v0.1.x Error-Handling Mechanism

v0.1.x uses two detection patterns:

| Error | Detection pattern | Location |
|-------|-------------------|----------|
| Division by zero | **Explicit pre-validation**: `if right == 0.0` before dividing | `evaluator.py` |
| Overflow | **Post-result NaN/Inf check**: `math.isinf(result) or math.isnan(result)` | `evaluator.py:_check_overflow()` |

Neither pattern touches `errno`. The division-by-zero guard is a domain pre-check;
the overflow guard is a post-compute NaN/Inf check. Both are fully portable.

---

## 4. Recommended Detection Strategy: Explicit Pre-Validation

**Use explicit pre-validation (input guards), consistent with the division-by-zero
pattern in v0.1.x.**

### Rationale

- Python's `math.sqrt(-1)` raises `ValueError: math domain error` and
  `math.log(0)` raises `ValueError: math domain error`. Catching `ValueError` from
  `math.*` calls would work, but it conflates domain errors from different sources
  and could accidentally swallow unrelated `ValueError`s.
- Explicit guards (`if x < 0` before sqrt, `if x <= 0` before log) are
  unambiguous, self-documenting, and match the v0.1.x division-by-zero pattern
  exactly. They require no exception catching for domain logic.
- Pre-validation is evaluated before the `math.*` call, so there is no risk of
  platform differences in how `libm` signals domain conditions through Python.
- Pre-call checking is more portable and keeps the domain rules co-located with
  the function definition, making them easy to audit and maintain.

### Decision: Pre-call validation (not exception catch, not post-call NaN/Inf check)

**Implementation sketch** (in the function-dispatch table in `evaluator.py`):

```python
def _eval_sqrt(x: float) -> float:
    if x < 0:
        raise DomainError()
    return math.sqrt(x)

def _eval_log(x: float) -> float:
    if x <= 0:
        raise DomainError()
    return math.log(x)
```

A new `DomainError(CalcError)` exception and a `"domain error"` entry in
`_MESSAGES` follow the existing pattern in `errors.py`.

---

## 5. Function-by-Function Domain Map

| Function | Domain restriction | Detection method | Raises |
|----------|--------------------|------------------|--------|
| `sqrt(x)` | x ≥ 0 | Pre-validate: `if x < 0` | `DomainError` |
| `log(x)` | x > 0 | Pre-validate: `if x <= 0` | `DomainError` |
| `abs(x)` | none | — | — |
| `floor(x)` | none | — | — |
| `ceil(x)` | none | — | — |
| `round(x)` | none | — | — |
| `sin(x)` | none (radians) | — | — |
| `cos(x)` | none (radians) | — | — |
| `tan(x)` | none (radians) — see §6 | — | — |
| `exp(x)` | none — see §6 | — | — |
| `pow(x, y)` | none per spec — see §6 | — | — |
| `atan2(y, x)` | none | — | — |

---

## 6. Edge Cases: tan, exp, pow

### `tan` near ±π/2

`math.tan(math.pi / 2)` in Python returns a very large finite float (~1.633e16),
not `inf`, because `math.pi / 2` is not the exact mathematical π/2. There is no
`OverflowError` or `ValueError`. The spec lists `tan` with no domain restriction and
does not include a tan-overflow acceptance test. **tan overflow is out of scope.**

Post-compute overflow detection (`_check_overflow`) already catches any result that
does become `inf`/`NaN`; that path raises the existing `Overflow` error, which is
correct and already tested.

### `exp` overflow

`math.exp(1000)` raises Python `OverflowError`, not a domain error. The spec lists
`exp` with no domain restriction, and `exp` overflow is already covered by the
inherited `overflow` error path. Wrap `exp` calls to catch `OverflowError` and
re-raise as `Overflow()` (same as v0.1.x overflow). **exp overflow is an arithmetic
overflow, not a domain error.**

### `pow(x, y)` with negative base and non-integer exponent

`math.pow(-2, 0.5)` raises `ValueError: math domain error` in Python. The v0.2.0
spec declares `pow`'s domain restriction as "none" and does not include this case
in the acceptance tests. **Negative-base pow with non-integer exponent is out of
scope for v0.2.0.**

---

## 7. Cross-Platform Confirmation

Pre-validation guards run before any `math.*` call and produce identical behaviour
on macOS and Linux. There are no cross-platform concerns for this detection
strategy: the guards are pure Python comparisons (`x < 0`, `x <= 0`) that do not
depend on `libm`, `errno`, or any platform-specific behaviour.

---

## 8. Summary of Recommendations

1. **Language is Python** — all C/C++ errno/math_errhandling concerns are
   irrelevant. Python normalises `math` errors to `ValueError`/`OverflowError`
   portably on macOS and Linux.

2. **Use explicit pre-validation** for `sqrt` (x < 0) and `log` (x ≤ 0). This
   matches the v0.1.x division-by-zero pattern and is unambiguous.

3. **Add `DomainError(CalcError)`** to `errors.py` with message `"domain error"`,
   following the existing error taxonomy.

4. **tan overflow, exp overflow, and negative-base pow** are not domain errors
   under the v0.2.0 spec. tan produces large-but-finite results. exp overflow is
   caught by the existing overflow path. Negative-base pow is out of scope.

5. **No cross-platform concern exists** for this detection strategy. Pre-validation
   guards run before any `math.*` call and produce identical behaviour on macOS and
   Linux.
