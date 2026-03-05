# Research: round(2.5) Tie-Breaking — Language Runtime vs Spec

**Issue:** #41
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## 1. Language

The project is implemented in **Python 3** (requires-python = ">=3.12", per `pyproject.toml`).

---

## 2. Python's Default round() Semantics

Python 3's built-in `round()` implements **round-half-to-even** (banker's rounding):

```python
round(0.5)   # → 0  (rounds to nearest even)
round(1.5)   # → 2  (rounds to nearest even)
round(2.5)   # → 2  (rounds to nearest even)
round(-0.5)  # → 0  (rounds to nearest even)
```

This **conflicts** with the v0.2.0 spec acceptance criterion:

> `calc 'round(2.5)'` must print `3` to stdout and exit 0.

The spec requires **round-half-away-from-zero** ("school" rounding).

---

## 3. Implementation Plan

Do **not** use Python's built-in `round()`. Instead, implement a custom helper using `math.floor` / `math.ceil`:

```python
import math

def _round_half_away(x: float) -> float:
    if x >= 0:
        return float(math.floor(x + 0.5))
    else:
        return float(math.ceil(x - 0.5))
```

This is a one-line conceptual fix (one helper function) wired into the evaluator's `round` dispatch.

**Verification:**

| Expression   | `_round_half_away` | Spec expectation |
|--------------|--------------------|-----------------|
| round(0.5)   | 1                  | 1               |
| round(1.5)   | 2                  | 2               |
| round(2.5)   | 3                  | 3               |
| round(-0.5)  | -1                 | -1              |
| round(-1.5)  | -2                 | -2              |
| round(-2.5)  | -3                 | -3              |

All half-integer values round away from zero, consistent with standard mathematical ("school") rounding.

---

## 4. Other Half-Integer Values in the Test Suite

The v0.2.0 spec acceptance criteria contain **only one explicit round test**:

```
calc 'round(2.5)' → 3
```

No other half-integer inputs appear in the current spec. However, the same discrepancy would surface for any x.5 input where x is even (0.5, 2.5, 4.5, …) — these are exactly the cases where Python's banker's rounding diverges from round-half-away-from-zero.

---

## 5. Conclusion

- **Language:** Python 3.12+
- **Default round semantics:** Banker's rounding (round-half-to-even) — **does not match spec**
- **Fix:** Replace `round(x)` with a `_round_half_away(x)` helper using `math.floor(x + 0.5)` for non-negative and `math.ceil(x - 0.5)` for negative values
- **Scope:** One helper function in the evaluator; all existing tests for integer inputs are unaffected

This is a P2 pre-implementation catch — a single deterministic acceptance-test failure if the built-in `round()` is used naively.
