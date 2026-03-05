# Research: Function Dispatch Table Design and Domain Error Detection

**Issue:** #54
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Recommendation

---

## 1. Registry Structure

### Recommendation: `FunctionEntry` dataclass with optional `domain_check` predicate

The minimal viable entry is `tuple[int, Callable]` (arity, fn). However, a richer
record is warranted because two functions (`sqrt`, `log`) require domain validation
that belongs logically alongside the function pointer, not scattered through the
evaluator.

**Recommended definition:**

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class FunctionEntry:
    name: str                                    # lookup key; matches lexer identifier
    arity: int                                   # expected argument count
    fn: Callable[..., float]                     # implementation pointer
    domain_check: Optional[Callable[..., bool]] = None  # None = no restriction
```

**Why not a plain `dict[str, tuple[int, Callable]]`?**

A bare tuple is sufficient if domain checking is handled entirely by catching
`ValueError` from `math.*` calls. But coupling domain logic to exception handling
from the standard library has three drawbacks:

1. It conflates library-level exceptions (`ValueError: math domain error`) with
   calculator-level errors, making the error taxonomy dependent on CPython internals.
2. A catch-all `except ValueError` in the evaluator could silently swallow
   unrelated `ValueError`s from future code.
3. It makes domain constraints invisible in the table — a reader cannot tell from
   the table alone which functions have restrictions.

The `domain_check` predicate field makes domain constraints explicit, co-located
with the function entry, and independently testable. For functions with no domain
restriction the field is `None` (zero overhead, clear intent).

**Concrete table (v0.2.0):**

```python
import math

FUNCTION_TABLE: list[FunctionEntry] = [
    FunctionEntry("sqrt",  1, math.sqrt,  lambda x: x >= 0),
    FunctionEntry("abs",   1, math.fabs,  None),
    FunctionEntry("floor", 1, math.floor, None),
    FunctionEntry("ceil",  1, math.ceil,  None),
    FunctionEntry("round", 1, round,      None),
    FunctionEntry("sin",   1, math.sin,   None),
    FunctionEntry("cos",   1, math.cos,   None),
    FunctionEntry("tan",   1, math.tan,   None),
    FunctionEntry("log",   1, math.log,   lambda x: x > 0),
    FunctionEntry("exp",   1, math.exp,   None),
    FunctionEntry("pow",   2, math.pow,   None),
    FunctionEntry("atan2", 2, math.atan2, None),
]

_FUNC_BY_NAME: dict[str, FunctionEntry] = {e.name: e for e in FUNCTION_TABLE}
```

The dict is built once at module load; lookup is O(1). Adding a new function in a
future version requires exactly one new `FunctionEntry` line.

---

## 2. Domain Error Detection Strategy

### Recommendation: Pre-validation predicate on `FunctionEntry`; do NOT catch `ValueError`

Python's `math.sqrt(-1)` and `math.log(0)` raise `ValueError: math domain error`.
Catching `ValueError` around `math.*` calls is technically workable but is not the
right approach (see rationale above). The `domain_check` predicate is run **before**
the `fn` call:

```python
if isinstance(node, FunctionCall):
    entry = _FUNC_BY_NAME.get(node.name)
    if entry is None:
        raise UnknownFunction(node.name)
    if len(node.args) != entry.arity:
        raise WrongArity(node.name, entry.arity)
    evaluated_args = [evaluate(arg) for arg in node.args]
    if entry.domain_check is not None and not entry.domain_check(*evaluated_args):
        raise DomainError()
    result = entry.fn(*evaluated_args)
    _check_overflow(result)
    return result
```

A new `DomainError(CalcError)` exception is added to `errors.py` with message
`"domain error"`, following the existing error taxonomy.

**Only `sqrt` and `log` have non-`None` predicates in v0.2.0:**

| Function | Predicate | Rejects |
|----------|-----------|---------|
| `sqrt`   | `x >= 0`  | negative inputs |
| `log`    | `x > 0`   | zero and negative inputs |
| all others | `None`  | no restriction |

---

## 3. Overflow vs Domain: `_check_overflow` Remains Correct for `exp`

There are two distinct failure paths:

| Path | Trigger | Detection | Error |
|------|---------|-----------|-------|
| Domain error | `sqrt(-1)`, `log(0)` — invalid input, `math.*` would raise `ValueError` | Pre-validation predicate before call | `DomainError` |
| Overflow | `exp(large)` — valid input, result is ±∞ | Post-compute `math.isinf`/`math.isnan` via `_check_overflow` | `Overflow` |

`math.exp(1000)` raises Python `OverflowError` (not `ValueError`) before
`_check_overflow` is reached. To keep the existing `Overflow` error path intact,
the evaluator should also catch `OverflowError` around `entry.fn(...)` and re-raise
as `Overflow()`:

```python
try:
    result = entry.fn(*evaluated_args)
except OverflowError:
    raise Overflow()
_check_overflow(result)
```

This ensures `exp` overflow is reported as `error: overflow`, not as an unhandled
Python exception. The `_check_overflow` guard then handles any function that returns
`inf`/`NaN` without raising (e.g. `math.tan` near ±π/2 produces large-but-finite
results — no action needed there).

**`_check_overflow` is correct and sufficient for all cases except `math.exp` with
large inputs**, which raises `OverflowError` before returning. A single
`except OverflowError` wrapper around `entry.fn(...)` covers this gap.

---

## 4. Arity Validation: Evaluator, Not Parser

### Recommendation: Validate arity in the evaluator at `FunctionCall` node dispatch

**Parser-time checking** has the appealing property of rejecting invalid call-sites
before AST construction. However, it requires the parser to import or query the
function table, coupling two otherwise independent modules. The existing parser has
zero knowledge of what functions exist; it parses `name(arg, arg, ...)` into a
`FunctionCall` node regardless of the name.

**Evaluator-time checking** keeps the parser independent: the parser emits any
`FunctionCall` node with any argument list; the evaluator resolves the name through
the table and enforces arity there. This is the standard pattern for interpreted
languages (Python itself validates argument count at call time, not parse time).

Trade-off summary:

| | Parser-time | Evaluator-time |
|---|---|---|
| Error is caught | Before AST is built | When node is evaluated |
| Parser–table coupling | Yes (parser must import table) | No |
| Handles dynamic dispatch | No (table must be static at parse time) | Yes |
| Implementation complexity | Higher (parser change required) | Lower (one check in evaluator) |

For a calculator with a static, load-time function table the practical difference is
negligible — both paths reject bad input before any output is produced. The
evaluator-time approach is preferred here because it maintains the existing
separation of concerns: the parser produces AST nodes; the evaluator enforces
semantics.

**Consequence:** the parser emits `FunctionCall(name="sqrt", args=[...])` for any
call expression. If `sqrt` is called with 2 arguments, the evaluator raises
`WrongArity("sqrt", expected=1)`.

---

## 5. Summary of Recommendations

| Question | Recommendation |
|----------|---------------|
| Registry type | `FunctionEntry` frozen dataclass with `name`, `arity`, `fn`, `domain_check` fields; indexed by `dict[str, FunctionEntry]` |
| Domain error detection | Pre-validation predicate (`domain_check`) on each entry; `None` for unrestricted functions; raises `DomainError` |
| `ValueError` from `math.*` | Do **not** catch; pre-validation prevents the call from reaching the math function for in-scope cases |
| `exp` overflow | Catch `OverflowError` from `entry.fn(...)` and re-raise as `Overflow()`; `_check_overflow` unchanged |
| `_check_overflow` | Remains correct for post-compute `inf`/`NaN` detection; no changes needed |
| Arity validation | In the **evaluator** at `FunctionCall` dispatch; parser stays table-agnostic |

---

## 6. New Errors Required

Add to `errors.py`:

```python
class DomainError(CalcError):
    """Raised when a function argument is outside the function's domain."""

class UnknownFunction(CalcError):
    """Raised when a called name is not in the function table."""

class WrongArity(CalcError):
    """Raised when argument count does not match function arity."""
```

Add to `_MESSAGES`:

```python
DomainError:      "domain error",
UnknownFunction:  "unknown function",
WrongArity:       "wrong number of arguments",
```

---

## 7. Follow-up Issues

- Add `FunctionCall` and `Name` AST node types to `parser.py`
- Add `DomainError`, `UnknownFunction`, `WrongArity` to `errors.py`
- Implement `FUNCTION_TABLE` and `_FUNC_BY_NAME` in `src/calc/functions.py`
- Update `evaluator.py` to dispatch `FunctionCall` and `Name` nodes through the table
- Add `OverflowError` catch around `entry.fn(...)` in the evaluator
