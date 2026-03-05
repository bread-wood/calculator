# Research: evaluate() Return Type — int | float Union from floor, ceil, round

**Issue:** #67
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Recommendation

---

## 1. Question Inventory

1. Should function-table wrappers normalize integer-returning functions to `float` via explicit `float()` casts?
2. Should `evaluate()` return type be updated to `float | int`? If so, what is the downstream impact on `format_result`'s type signature?
3. Does the v0.1.x codebase run mypy or pyright as part of `make test` or CI?
4. Is `_round_half_away` defined to return `float`, keeping the `round` entry homogeneous?

---

## 2. CI Type-Checker Audit

### Makefile

```makefile
test: build
    uv run pytest tests/ -v

lint:
    uv run ruff check src/ tests/
```

`make test` runs only **pytest**. `make lint` runs only **ruff** (a linter/formatter, not a type checker).

### pyproject.toml

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "ruff>=0.15.4",
]
```

Neither **mypy** nor **pyright** appear in `pyproject.toml` as a dev dependency. No `[tool.mypy]` or `[tool.pyright]` sections are present. No CI configuration file (`.github/workflows/`) was observed in the worktree.

**Conclusion: No static type checker runs in CI or as part of `make test` / `make lint` in v0.1.x.**

This means type-annotation decisions are about code correctness and readability, not about failing automated checks. There is currently no enforcement gate that would break if `evaluate()` returns an `int` where `float` is declared.

---

## 3. Python Return Types for floor, ceil, round

In CPython 3.x (required: `>=3.12`):

| Function | Return type | Example |
|---|---|---|
| `math.floor(x)` | `int` | `math.floor(2.7)` → `2` |
| `math.ceil(x)` | `int` | `math.ceil(2.3)` → `3` |
| `math.fabs(x)` | `float` | `math.fabs(-5)` → `5.0` |
| `math.sqrt(x)` | `float` | `math.sqrt(4)` → `2.0` |
| `_round_half_away(x)` | `float` (by spec) | `_round_half_away(2.5)` → `3.0` |

`math.floor` and `math.ceil` return Python `int` objects, not `float`. The stub in `typeshed` reflects this: `def floor(__x: float) -> int`.

---

## 4. `_round_half_away` Return Type

Research #41 specifies:

```python
def _round_half_away(x: float) -> float:
    if x >= 0:
        return float(math.floor(x + 0.5))
    else:
        return float(math.ceil(x - 0.5))
```

The explicit `float(...)` wrap means `_round_half_away` returns `float` for all inputs. This is intentional per the spec; the helper is already homogeneous with the arithmetic evaluator's `float` contract.

---

## 5. Runtime Safety of Passing `int` to `format_result(value: float)`

`format_result` performs:

```python
if math.trunc(value) == value:
    return str(int(value))
```

`math.trunc(2)` → `2`; `2 == 2` → `True`. Python's `int` passes through the integer-detection branch without error. Research #44 confirms this explicitly. **No runtime error occurs if `format_result` receives a Python `int`.**

However:
- The declared type `value: float` is inaccurate if `int` is passed.
- If a type checker is added later, callers that pass `math.floor(...)` output directly would be flagged.

---

## 6. Function Table Type Homogeneity

Research #54 defines:

```python
@dataclass(frozen=True)
class FunctionEntry:
    fn: Callable[..., float]
```

`math.floor` is typed `(float) -> int` in typeshed. Storing it as `Callable[..., float]` is a type mismatch detectable by mypy/pyright. Even without a current CI checker, this discrepancy would be immediately visible if type checking is added in v0.2.x or later.

---

## 7. Analysis: float() Wrapper vs. Annotating evaluate() as int | float

### Option A — float() wrappers in the function table (keep evaluate() -> float)

```python
FunctionEntry("floor", 1, lambda x: float(math.floor(x)), None)
FunctionEntry("ceil",  1, lambda x: float(math.ceil(x)),  None)
```

| Dimension | Assessment |
|---|---|
| `evaluate()` return type | Stays `-> float` — accurate, no change needed |
| `format_result` signature | No change — already `value: float` |
| `FunctionEntry.fn` type | Homogeneous `Callable[..., float]` — no mismatch |
| Runtime cost | One extra C-level `float()` call per invocation — negligible |
| Future type-checker readiness | Clean — zero new warnings if mypy/pyright added |
| Semantic transparency | Minor: hides that floor/ceil are whole-valued; mitigated by function name |
| `_round_half_away` alignment | Consistent — spec #41 already uses `float(math.floor(...))` wrapper |

### Option B — Update evaluate() to int | float (no wrappers)

```python
def evaluate(node: ASTNode) -> int | float:
    ...
```

| Dimension | Assessment |
|---|---|
| `evaluate()` return type | More precise; reflects actual runtime values |
| `format_result` signature | Must be updated to `value: int \| float` for type accuracy |
| `FunctionEntry.fn` type | Must be updated to `Callable[..., int \| float]`; typeshed `math.floor` is already `-> int` so this is accurate |
| `_check_overflow` | Currently typed `result: float`; `math.isinf` and `math.isnan` accept `int` but pyright may warn |
| Future type-checker readiness | Requires broader annotation updates across evaluator, format_result, and _check_overflow |
| Semantic transparency | Accurate — callers know floor/ceil return integers |
| `_round_half_away` alignment | Inconsistent — the helper returns `float`, so `round` entry would differ from `floor`/`ceil` |

### Option C — Both wrappers and updated annotation (unnecessary)

Applying `float()` wrappers and also changing `evaluate() -> float | int` would be contradictory: if wrappers guarantee float output, the union annotation would be incorrect. This option is rejected.

---

## 8. Recommendation

**Use float() wrappers in the function table (Option A). Keep `evaluate() -> float`.**

Rationale:

1. **No type checker in CI.** There is no mypy or pyright gate to enforce. The decision is therefore driven by correctness, consistency, and forward maintainability.

2. **`_round_half_away` already uses float() wrapping** per spec #41 (`float(math.floor(x + 0.5))`). Applying the same pattern to `floor` and `ceil` makes the entire function table uniform.

3. **`FunctionEntry.fn: Callable[..., float]` stays accurate.** Research #54's table definition requires homogeneous return types. `float()` wrappers satisfy this without changing the dataclass.

4. **`evaluate() -> float` stays accurate.** All dispatch paths — arithmetic, unary, and function-call — return `float`. No downstream changes needed to `format_result`, `_check_overflow`, or any caller.

5. **Runtime overhead is negligible.** `float()` applied to a Python `int` is a single CPython C-level call. For a calculator this cost is immeasurable.

6. **Forward-compatible.** If mypy or pyright is added to CI in a future milestone, the codebase will be immediately clean. Option B would require coordinated annotation updates across multiple functions.

### Concrete table entries

```python
FunctionEntry("floor", 1, lambda x: float(math.floor(x)), None),
FunctionEntry("ceil",  1, lambda x: float(math.ceil(x)),  None),
FunctionEntry("round", 1, _round_half_away,                None),
```

`_round_half_away` returns `float` by its own spec; no wrapper needed.

---

## 9. Downstream Impact on format_result

No change required. `format_result(value: float)` remains correct:

- Arithmetic results: `float` — unchanged.
- `floor(2.7)`: with wrapper → `2.0` (float) → `math.trunc(2.0) == 2.0` → `True` → outputs `"2"`.
- `ceil(2.3)`: with wrapper → `3.0` (float) → outputs `"3"`.
- `_round_half_away(2.5)`: → `3.0` (float) → outputs `"3"`.

The `.15g` precision bug documented in research #44 is a separate issue and is out of scope here.

---

## 10. Summary of Answers

| Question | Answer |
|---|---|
| Use float() wrappers for floor/ceil? | **Yes.** `lambda x: float(math.floor(x))` and `lambda x: float(math.ceil(x))` keep the table homogeneous and evaluate() return type accurate. |
| Update evaluate() to float \| int? | **No.** With float() wrappers, evaluate() correctly returns float on all paths; no annotation change needed. |
| Does CI run mypy or pyright? | **No.** Only pytest and ruff (linter) are in the Makefile and pyproject.toml dev dependencies. |
| Is _round_half_away defined to return float? | **Yes.** Research #41 specifies `float(math.floor(x + 0.5))` — already returns float; no wrapper needed in the function table. |

---

## 11. Follow-up Issues

None spawned. The recommendation is implementable within the existing v0.2.0 issue scope using the function table from research #54 with the lambda wrappers specified above.
