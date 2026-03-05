# Low-Level Design: evaluator (v0.2.0)

**Module:** `evaluator`
**File:** `src/calc/evaluator.py`
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Draft

---

## Overview

The `evaluator` module walks a typed AST produced by the parser and returns a `float`
result. In v0.2.0 it gains three new responsibilities:

1. **Constant resolution** — `Name` AST nodes are looked up in `_DEFAULT_ENV`
   (a module-level dict seeded with `math.pi` and `math.e`).
2. **Function dispatch** — `Call` AST nodes are dispatched through `_FUNCTION_TABLE`,
   which maps names to `FunctionEntry` records carrying arity, a function pointer, and
   an optional domain-check predicate.
3. **Domain and arity validation** — enforced in the evaluator at call time (not in the
   parser), keeping the parser table-agnostic.

The module also owns `format_result`, which converts the final `float` to the
canonical output string.

**What this module does NOT do:**

- It does not scan or parse input; those responsibilities belong to `lexer` and `parser`.
- It does not print to stdout or stderr; output is the caller's responsibility.
- It does not handle CLI argument validation; that belongs to `__main__`.
- It does not define error base classes or message formatting; those belong to `errors`.
- It does not support user-defined variables or assignment in v0.2.0, though `env` is
  designed to accommodate them without a signature change.

---

## Resolving HLD Open Questions

### OQ-1: `functions.py` vs inline in `evaluator.py`

**Decision: keep `FunctionEntry`, `FUNCTION_TABLE`, and `_DEFAULT_ENV` inline in
`evaluator.py`.**

Rationale:
- `_FUNCTION_TABLE` is consumed exclusively by `evaluator.py`; no other module imports
  it. A separate `functions.py` would add a file without reducing coupling.
- `_DEFAULT_ENV` is semantically part of the evaluator's runtime environment, not a
  standalone data store.
- Keeping everything in one file avoids a potential circular import: if `functions.py`
  were to import `FunctionEntry` from `evaluator.py`, or vice versa, the import graph
  would need careful ordering. Inline eliminates the issue entirely.
- Research #39 suggests a dedicated module for discoverability; however, the project has
  12 functions in a single evaluator. The discoverability benefit does not outweigh the
  added file.

If the function table grows significantly in a future milestone, extracting it to
`functions.py` remains a clean refactor with no API change.

### OQ-2: `UnknownName` vs `UnknownFunction` for bare-identifier lookup miss

**Decision: use a new `UnknownName(name: str)` error class for `Name` nodes that fail
env lookup; keep `UnknownFunction(name: str)` exclusively for `Call` nodes whose name
is absent from `_FUNCTION_TABLE`.**

Rationale:
- Semantically, `log` (bare, no parens) and `log(x)` are different syntactic forms.
  Using `UnknownFunction` for both would conflate a missing variable binding with a
  missing function definition.
- The spec does not mandate an error message for an unrecognised bare identifier; a
  distinct `UnknownName` class gives implementors the freedom to word the message
  appropriately (`"unknown name: log"` vs `"unknown function: log"`).
- Research #56 explicitly proposes `UnknownName` for this case.

### OQ-3: `_check_overflow` after `OverflowError` catch for `exp`

**Decision: both are needed; they cover different failure modes.**

- `math.exp(1000)` raises Python `OverflowError` *before* returning. A
  `try/except OverflowError` around `entry.fn(...)` catches this and re-raises as
  `Overflow()`.
- Other functions (e.g. a future function that returns `float('inf')` without raising)
  are caught by the post-call `_check_overflow(result)`.
- Research #54 confirms this two-layer strategy.

---

## Public Interface

### `evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float`

Recursively walks `node` and returns the `float` result.

| Parameter | Type | Description |
|-----------|------|-------------|
| `node` | `ASTNode` | Root of the AST subtree to evaluate |
| `env` | `dict[str, float] \| None` | Symbol table for `Name` node resolution; defaults to `_DEFAULT_ENV` when `None` |

**Returns:** `float`

**Raises:**
- `DivisionByZero` — right operand of `/` is `0.0`
- `Overflow` — result is `±inf` or `NaN`, or `math.exp` raises `OverflowError`
- `DomainError` — function argument fails its `domain_check` predicate
- `UnknownFunction(name)` — `Call` node name not found in `_FUNCTION_TABLE`
- `WrongArity(name, expected)` — argument count does not match `FunctionEntry.arity`
- `UnknownName(name)` — bare `Name` node identifier not found in `env`
- `TypeError` — unrecognised AST node type (programming error, not user error)

**Signature rationale:** Using `env=None` (not `env=_DEFAULT_ENV`) as the default
avoids sharing a mutable dict across calls. The sentinel-substitution pattern is
idiomatic Python. All existing call sites (`evaluate(ast)`) continue to work without
modification (research #56).

---

### `format_result(value: float) -> str`

Converts a `float` to the canonical output string.

| Parameter | Type | Description |
|-----------|------|-------------|
| `value` | `float` | The evaluated result |

**Returns:** A string using integer notation for whole-valued results (e.g. `"3"`,
`"1024"`), or `str(value)` for decimals (e.g. `"1.4142135623730951"`).

**Raises:** Nothing.

**Format rules:**
1. If `math.trunc(value) == value`, return `str(int(value))`.
2. Otherwise return `str(value)`.

`str(float)` in CPython uses David Gay's dtoa algorithm — the shortest round-trip
decimal string, matching all spec-mandated decimal outputs. The previous
`f"{value:.15g}"` approach truncated the last 1–2 significant digits; it is replaced
with `str(value)` (research #44, #57).

---

### `_DEFAULT_ENV: dict[str, float]`

Module-level constant table. Read-only in v0.2.0.

```python
_DEFAULT_ENV: dict[str, float] = {
    "pi": math.pi,   # 3.141592653589793
    "e":  math.e,    # 2.718281828459045
}
```

Callers may pass a custom dict to support future user-defined variables. The module
never mutates `_DEFAULT_ENV`.

---

### `_FUNCTION_TABLE: dict[str, FunctionEntry]`

Module-level dict built from `FUNCTION_TABLE` list at import time. Used exclusively
by `evaluate()` to dispatch `Call` nodes.

---

## Data Structures

### `FunctionEntry` (frozen dataclass)

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class FunctionEntry:
    name: str                                         # matches lexer IDENT token
    arity: int                                        # expected argument count
    fn: Callable[..., float]                          # implementation pointer
    domain_check: Optional[Callable[..., bool]] = None  # None = no restriction
```

**Field invariants:**

| Field | Invariant |
|-------|-----------|
| `name` | Non-empty; matches the string produced by `_scan_ident()` in the lexer |
| `arity` | ≥ 0; for v0.2.0 all entries use 1 or 2 |
| `fn` | Returns `float`; `floor`/`ceil` use `lambda x: float(math.floor/ceil(x))` to maintain homogeneity (research #67) |
| `domain_check` | If not `None`, called with the evaluated args *before* `fn`; returns `True` if the call is safe |

**Concrete table (v0.2.0):**

```python
FUNCTION_TABLE: list[FunctionEntry] = [
    FunctionEntry("sqrt",  1, math.sqrt,                     lambda x: x >= 0),
    FunctionEntry("abs",   1, math.fabs,                     None),
    FunctionEntry("floor", 1, lambda x: float(math.floor(x)), None),
    FunctionEntry("ceil",  1, lambda x: float(math.ceil(x)),  None),
    FunctionEntry("round", 1, _round_half_away,               None),
    FunctionEntry("sin",   1, math.sin,                      None),
    FunctionEntry("cos",   1, math.cos,                      None),
    FunctionEntry("tan",   1, math.tan,                      None),
    FunctionEntry("log",   1, math.log,                      lambda x: x > 0),
    FunctionEntry("exp",   1, math.exp,                      None),
    FunctionEntry("pow",   2, math.pow,                      None),
    FunctionEntry("atan2", 2, math.atan2,                    None),
]

_FUNCTION_TABLE: dict[str, FunctionEntry] = {e.name: e for e in FUNCTION_TABLE}
```

Adding a new function in a future version requires exactly one new `FunctionEntry`
line. No parser or CLI changes are needed.

---

## Key Algorithms and Logic

### AST Dispatch Flow

```
evaluate(node, env)
        │
        ├─ isinstance(node, Number)
        │       └─ return node.value
        │
        ├─ isinstance(node, Name)
        │       └─ env.get(node.name)
        │               ├─ found  → return value
        │               └─ None   → raise UnknownName(node.name)
        │
        ├─ isinstance(node, Call)
        │       └─ entry = _FUNCTION_TABLE.get(node.func)
        │               ├─ None           → raise UnknownFunction(node.func)
        │               ├─ arity mismatch → raise WrongArity(node.func, entry.arity)
        │               ├─ domain_check fails → raise DomainError()
        │               ├─ OverflowError from entry.fn() → raise Overflow()
        │               └─ result → _check_overflow(result); return result
        │
        ├─ isinstance(node, UnaryOp) and node.op == '-'
        │       └─ result = -evaluate(node.operand, env)
        │               └─ _check_overflow(result); return result
        │
        ├─ isinstance(node, BinaryOp)
        │       ├─ left  = evaluate(node.left, env)
        │       ├─ right = evaluate(node.right, env)
        │       ├─ op '/' → right == 0.0 → raise DivisionByZero()
        │       └─ result → _check_overflow(result); return result
        │
        └─ else → raise TypeError("Unknown node type: ...")
```

### Function Call Dispatch (detailed)

```python
if isinstance(node, Call):
    entry = _FUNCTION_TABLE.get(node.func)
    if entry is None:
        raise UnknownFunction(node.func)
    if len(node.args) != entry.arity:
        raise WrongArity(node.func, entry.arity)
    evaluated_args = [evaluate(arg, env) for arg in node.args]
    if entry.domain_check is not None and not entry.domain_check(*evaluated_args):
        raise DomainError()
    try:
        result = entry.fn(*evaluated_args)
    except OverflowError:
        raise Overflow()
    _check_overflow(result)
    return result
```

**Why evaluate args before domain check?** The domain check predicate is a simple
scalar comparison on the evaluated values. Evaluating args first is natural and allows
nested expressions like `sqrt(4 - 5)` to be checked against the correct numeric value.

**Why args are evaluated left-to-right:** Python list comprehensions evaluate
left-to-right; for `pow(a, b)` and `atan2(y, x)` this matches standard mathematical
convention and produces deterministic error ordering for multi-arg errors.

### `_round_half_away(x: float) -> float`

Python's built-in `round()` uses banker's rounding (round-half-to-even), which would
produce `round(2.5) → 2`. The spec requires `round(2.5) → 3` (round-half-away-from-zero,
research #41, #75).

```python
def _round_half_away(x: float) -> float:
    if x >= 0:
        return float(math.floor(x + 0.5))
    else:
        return float(math.ceil(x - 0.5))
```

**Verification table:**

| Input | `_round_half_away` | Python `round()` | Spec expects |
|-------|--------------------|------------------|--------------|
| 0.5   | 1.0                | 0                | 1            |
| 1.5   | 2.0                | 2                | 2            |
| 2.5   | 3.0                | 2                | 3            |
| -0.5  | -1.0               | 0                | -1           |
| -1.5  | -2.0               | -2               | -2           |
| -2.5  | -3.0               | -2               | -3           |

### Overflow Detection (two layers)

| Layer | Trigger | Mechanism |
|-------|---------|-----------|
| `except OverflowError` around `entry.fn()` | `math.exp(large)` raises before returning | re-raise as `Overflow()` |
| `_check_overflow(result)` post-call | Any function returning `±inf` or `NaN` | `math.isinf(result) or math.isnan(result)` |

`_check_overflow` is also applied after all arithmetic `BinaryOp` and `UnaryOp`
computations, unchanged from v0.1.x.

### Domain Validation

Only `sqrt` and `log` have non-`None` `domain_check` predicates in v0.2.0:

| Function | Predicate | Rejects |
|----------|-----------|---------|
| `sqrt`   | `x >= 0`  | negative inputs |
| `log`    | `x > 0`   | zero and negative inputs |

For functions like `tan` near ±π/2: `math.tan(math.pi / 2)` returns a very large
finite float in CPython (not `inf`), so `_check_overflow` does not trigger. This is
acceptable; the spec has no tan-overflow acceptance test (research #40).

For `pow(-2, 0.5)`: `math.pow` raises `ValueError` for a negative base with a
non-integer exponent. This case is out of scope for v0.2.0 (research #40, #74).

---

## Internal Structure

### File Layout

All code lives in `src/calc/evaluator.py`. No sub-modules.

```
evaluator.py
│
├─ imports: math, parser (ASTNode nodes), errors (CalcError subclasses)
│
├─ FunctionEntry        frozen dataclass
├─ _round_half_away()   private helper — round-half-away-from-zero
├─ FUNCTION_TABLE       list[FunctionEntry] — 12 entries
├─ _FUNCTION_TABLE      dict[str, FunctionEntry] — built from FUNCTION_TABLE
├─ _DEFAULT_ENV         dict[str, float] — {"pi": ..., "e": ...}
│
├─ evaluate()           public — recursive AST walker
├─ format_result()      public — float-to-string formatter
└─ _check_overflow()    private — NaN/inf guard
```

### Private Helpers

| Helper | Purpose |
|--------|---------|
| `_round_half_away(x)` | Round-half-away-from-zero implementation; used as `fn` for the `round` entry |
| `_check_overflow(result)` | Raises `Overflow` if `result` is `±inf` or `NaN`; called after all arithmetic and function calls |

---

## Error Handling

### Errors raised by this module

| Error | Condition | Research |
|-------|-----------|---------|
| `DivisionByZero` | `BinaryOp('/')` with `right == 0.0` | inherited from v0.1.x |
| `Overflow` | `_check_overflow` detects `isinf` or `isnan`, or `OverflowError` from `entry.fn()` | inherited + extended for exp |
| `DomainError` | `domain_check(*evaluated_args)` returns `False` | #40, #54 |
| `UnknownFunction(name)` | `Call` node name absent from `_FUNCTION_TABLE` | #54, #55 |
| `WrongArity(name, expected)` | `len(node.args) != entry.arity` | #54, #55 |
| `UnknownName(name)` | `Name` node identifier absent from `env` | #56 |
| `TypeError` | Unrecognised AST node type | programming error; not user-visible |

### Errors from dependencies

| Source | Exception | Treatment |
|--------|-----------|-----------|
| `math.exp` | `OverflowError` | caught at `entry.fn()` call site; re-raised as `Overflow()` |
| `math.sqrt`, `math.log` | `ValueError` | **not caught** — domain_check prevents the call from reaching math for in-scope cases; if reached by a bug, the unhandled `ValueError` is a programming error |
| `parser` AST nodes | `TypeError` from `isinstance` fallthrough | propagates unchanged; unrecognised node is a parser bug |

The evaluator never catches `ValueError` from `math.*` functions. Pre-validation
predicates (`domain_check`) are the sole domain-error detection mechanism. This
matches the v0.1.x `DivisionByZero` pattern and avoids conflating library exceptions
with calculator errors (research #40, #54).

---

## Testing Strategy

### Unit Tests (`tests/test_evaluator.py`)

#### Function and constant dispatch (14 cases)

One parametrized test case per supported function plus `pi` and `e`:

| Expression | Expected output |
|------------|----------------|
| `sqrt(9)` | `3.0` |
| `sqrt(2)` | `1.4142135623730951` |
| `abs(-5)` | `5.0` |
| `floor(2.7)` | `2.0` |
| `ceil(2.3)` | `3.0` |
| `round(2.5)` | `3.0` |
| `sin(0)` | `0.0` |
| `cos(0)` | `1.0` |
| `log(1)` | `0.0` |
| `exp(0)` | `1.0` |
| `pow(2, 10)` | `1024.0` |
| `atan2(1, 1)` | `0.7853981633974483` |
| `pi` | `3.141592653589793` |
| `e` | `2.718281828459045` |

#### Error-raise paths (5 cases)

| Expression | Raises | Condition |
|------------|--------|-----------|
| `sqrt(-1)` | `DomainError` | domain_check fails |
| `log(0)` | `DomainError` | domain_check fails |
| `unknownfn(1)` | `UnknownFunction("unknownfn")` | not in table |
| `sqrt(1, 2)` | `WrongArity("sqrt", 1)` | arity mismatch |
| `xyz` | `UnknownName("xyz")` | not in env |

#### `_round_half_away` (6 cases)

Test all half-integer boundaries from the verification table above.

#### `format_result` (key cases)

| Input | Expected |
|-------|----------|
| `3.0` | `"3"` |
| `1024.0` | `"1024"` |
| `1.4142135623730951` | `"1.4142135623730951"` |
| `3.141592653589793` | `"3.141592653589793"` |
| `2.718281828459045` | `"2.718281828459045"` |
| `0.7853981633974483` | `"0.7853981633974483"` |

#### Custom `env` passthrough

Verify that `evaluate(Name("x"), {"x": 42.0})` returns `42.0`; ensures the signature
supports future variable injection without implicit reliance on `_DEFAULT_ENV`.

### What to mock

Nothing. `evaluate` is a pure function over the AST; `math.*` is deterministic
stdlib. No I/O, no external state. Mocking would add complexity without benefit.

### Integration Tests (`tests/test_cli.py`)

All 21 spec acceptance criteria are tested end-to-end via subprocess:

- 16 success cases (function calls, constants, nested expressions)
- 5 error cases (domain error, unknown function, wrong arity)

These tests verify the full pipeline including `format_result` output formatting.

### Trickiest test cases

1. **`round(2.5)` → `"3"`**: exercises `_round_half_away` and confirms the custom
   implementation is wired in; Python's built-in `round(2.5)` returns `2`.
2. **`sqrt(2)` → `"1.4142135623730951"`**: exercises `str(value)` decimal formatting;
   the old `:.15g` format would return `"1.4142135623731"`.
3. **`exp(10000)` → `"error: overflow"`**: exercises the `OverflowError` catch path
   around `entry.fn()`; without the catch this would be an unhandled Python exception.
4. **`pi` → `"3.141592653589793"`**: exercises `Name` node lookup in `_DEFAULT_ENV`
   and `str(value)` formatting.
5. **`atan2(1, 1)` → `"0.7853981633974483"`**: exercises 2-arity dispatch and decimal
   formatting.

---

## Dependencies

| Dependency | Kind | Used for |
|------------|------|---------|
| `calc.parser` | internal | `ASTNode` union type; `Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call` dataclasses |
| `calc.errors` | internal | `DivisionByZero`, `Overflow`, `DomainError`, `UnknownFunction`, `WrongArity`, `UnknownName` |
| `math` | stdlib | `math.pi`, `math.e`, and all math function implementations |
| `dataclasses` | stdlib | `@dataclass(frozen=True)` for `FunctionEntry` |
| `typing` | stdlib | `Callable`, `Optional` for `FunctionEntry` field types |

No third-party dependencies. No import of `lexer`; the evaluator operates only on the
typed AST produced by the parser.
