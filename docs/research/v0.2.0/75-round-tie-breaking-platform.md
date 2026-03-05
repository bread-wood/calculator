# Research: round(2.5) Tie-Breaking — Platform Behavior Must Match Spec Output of 3

**Issue:** #75
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## 1. Platform & Language

- **Platform tested:** macOS Darwin arm64
- **Python version:** 3.13.5 (consistent with requires-python >= 3.12 in pyproject.toml)
- **Implementation language:** Python 3

---

## 2. Python Default round() — Confirmed Banker's Rounding

Python 3's built-in `round()` implements **round-half-to-even** (banker's rounding):

```
Python 3.13.5 on macOS arm64:
round(0.5)  → 0   (even)
round(1.5)  → 2   (even)
round(2.5)  → 2   (even) ← FAILS spec requirement of 3
round(3.5)  → 4   (even)
round(-0.5) → 0
round(-2.5) → -2
```

The spec requires `calc 'round(2.5)'` to print `3`. The Python built-in **does not satisfy this requirement**.

This behavior is **platform-independent** — Python's banker's rounding is defined by the language spec, not the OS. The result is the same on macOS and Linux.

---

## 3. Correct Substitute: round-half-away-from-zero

Use a custom helper that implements **round-half-away-from-zero** ("school" rounding):

```python
import math

def _round_half_away(x: float) -> float:
    if x >= 0:
        return float(math.floor(x + 0.5))
    else:
        return float(math.ceil(x - 0.5))
```

**Verification on macOS arm64 (Python 3.13.5):**

| Input | `_round_half_away` | Python `round()` | Spec |
|-------|-------------------|-----------------|------|
| 0.5   | 1.0               | 0               | 1    |
| 1.5   | 2.0               | 2               | 2    |
| 2.5   | **3.0**           | 2               | **3** |
| 3.5   | 4.0               | 4               | 4    |
| -0.5  | -1.0              | 0               | n/a  |
| -2.5  | -3.0              | -2              | n/a  |

`math.floor` and `math.ceil` are part of the C math library and produce consistent results across macOS and Linux.

---

## 4. round(-2.5) — Undocumented Negative Half Behavior

The spec contains no test for negative half-integers. The `_round_half_away` helper gives:

- `round(-2.5)` → **-3** (away from zero, symmetric with positive)

This is the mathematically expected result for round-half-away-from-zero and is consistent across positive and negative inputs. It should be documented as the intended behavior when round is implemented.

---

## 5. Output Formatting Interaction

The v0.1.x `format_result` function in `evaluator.py` uses:

```python
def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    ...
```

`_round_half_away(2.5)` returns `3.0` (a float). Since `math.trunc(3.0) == 3.0`, `format_result` converts it to `int(3.0)` = `3` and returns the string `"3"` — **not** `"3.0"`.

The formatting pipeline is fully compatible with the rounding helper. No changes to `format_result` are needed.

---

## 6. Recommendation

- **Do not** use Python's built-in `round()` for the `round` function implementation.
- **Use** `_round_half_away(x)` (via `math.floor`/`math.ceil`) in the evaluator's function dispatch for `round`.
- **Document** that the implementation uses round-half-away-from-zero, which gives `round(-2.5) = -3`.
- This is a single helper function; all existing non-half-integer inputs are unaffected.

---

## 7. Conclusion

| Question | Answer |
|----------|--------|
| Default Python round(2.5) | 2 (banker's rounding — fails spec) |
| Correct substitute | `math.floor(x + 0.5)` for x ≥ 0, `math.ceil(x - 0.5)` for x < 0 |
| round(-2.5) result | -3 (round-half-away-from-zero, symmetric) |
| format_result interaction | No issue: `format_result(3.0)` → `"3"` (integer output) |
| Platform consistency | math.floor/ceil are C stdlib; consistent on macOS and Linux |
