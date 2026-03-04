# Numeric Representation and Output Formatting

**Issue:** #5
**Milestone:** v0.1.0
**Date:** 2026-03-04

---

## Recommendation

Use **float64 (double)** as the single internal numeric type. Format output by checking if the result is a whole number: if `result == math.Trunc(result)`, print as integer using `%d` on the int64 cast; otherwise print as decimal using `%g` (or equivalent) to strip trailing zeros. Detect overflow via `math.IsInf(result)`.

---

## Evaluation

### Internal Type

#### float64 (Recommended)

- Single type handles all spec cases: `10/4 → 2.5`, `4/2 → 2`, `2+3 → 5`
- Division is always floating-point — no integer-truncation bug
- Overflow detection: `math.IsInf(result, 0)` after each operation
- Division by zero: `1.0 / 0.0` yields `+Inf` in IEEE 754 — catch this explicitly before dividing
- Representable integer range: exact integers up to 2^53 (9,007,199,254,740,992). The spec does not mention multi-digit overflow inputs, but any result larger than 2^53 will lose integer precision. This is acceptable for v0.1.0; overflow via `IsInf` covers the actual overflow case.
- **Tradeoff:** integer inputs like `4 / 2` compute as `4.0 / 2.0 = 2.0`, requiring post-computation formatting to suppress `.0`. This is trivial to implement.

#### Separate int/float with promotion

- Preserves exact integer arithmetic for integer-only expressions, removing the >2^53 imprecision concern
- Adds type-tracking complexity in the evaluator: every operator must handle int×int, int×float, float×int, float×float cases
- Not justified for v0.1.0 scope; adds friction for future extension (functions like `sqrt` return float regardless)
- **Not recommended**

#### Arbitrary precision (big.Float / GMP)

- Eliminates all overflow for practical inputs
- Adds significant complexity; big.Float requires explicit precision management and has no natural "is this a whole number" check
- External dep (GMP) violates the spec constraint "no external runtime dependencies beyond the standard library"
- **Not recommended**

---

### Output Formatting

#### Whole-number detection

```
if result == math.Trunc(result) → integer output
else → decimal output
```

This is correct for all values representable in float64. `math.Floor` is equivalent for positive numbers but `math.Trunc` is correct for negatives too.

#### Integer output

```go
fmt.Sprintf("%d", int64(result))
```

Correct for values in [−2^53, 2^53]. For values outside that range the float64 has already lost precision, but by that point `IsInf` has not triggered — this is an edge case the spec does not test and is acceptable for v0.1.0.

#### Decimal output

`%g` in Go/C strips trailing zeros and suppresses the trailing decimal point when not needed, but it switches to scientific notation for large/small exponents. To avoid scientific notation while still stripping trailing zeros:

```go
s := strconv.FormatFloat(result, 'f', -1, 64)
```

`strconv.FormatFloat` with format `'f'` and precision `-1` uses the minimum number of digits to represent the value exactly, with no trailing zeros beyond what is needed. This gives:
- `2.5` for `10/4` ✓
- `1.1` for `1.10` (input) ✓
- No scientific notation ✓

`%g` is simpler but switches to `%e` for values with exponent ≥ precision (default 6 significant digits truncation). For `strconv.FormatFloat(x, 'f', -1, 64)`, the behavior is well-defined and spec-safe.

**In C**, use `printf("%.15g", result)` with a post-format trailing-zero strip, or use `snprintf` + manual strip. The `%g` format with sufficient precision and a trailing-zero-strip function is the idiomatic approach.

#### Summary of formatting logic (language-agnostic pseudocode)

```
if IsInf(result) or IsNaN(result):
    error("overflow")
if result == Trunc(result) and result fits int64:
    print int64(result)
else:
    print FormatFloat(result, no trailing zeros, no sci notation)
```

---

### Overflow Detection

- After every arithmetic operation, check `math.IsInf(result, 0)`
- Division by zero must be caught **before** the division (check denominator == 0), not after — otherwise the language may panic (integer division) or return Inf silently
- `math.IsNaN` should also be guarded: `0.0 / 0.0` in IEEE 754 yields NaN; treat as overflow or as a separate internal error
- No pre-check needed for `+`, `-`, `*` — post-operation `IsInf` is sufficient

---

## Acceptance Criteria Mapping

| Spec case | float64 + formatting |
|-----------|----------------------|
| `10 / 4 → 2.5` | `10.0/4.0 = 2.5`; not whole number; FormatFloat → `"2.5"` ✓ |
| `4 / 2 → 2` | `4.0/2.0 = 2.0`; whole number; int64 cast → `"2"` ✓ |
| `2 + 3 → 5` | `5.0`; whole number → `"5"` ✓ |
| `1 / 0 → error: division by zero` | denominator == 0 check before divide ✓ |
| Overflow → `error: overflow` | `IsInf` post-operation ✓ |

---

## Decision

**Use float64. Detect whole numbers with `Trunc` comparison. Format integers as `%d`, decimals with `FormatFloat(f, -1)` (Go) or `%.15g`+trailing-zero-strip (C). Catch division-by-zero before dividing, overflow via `IsInf` after.**
