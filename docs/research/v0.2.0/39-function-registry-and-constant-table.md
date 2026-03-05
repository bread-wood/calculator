# Research: Function Registry and Constant Table Design

**Issue:** #39
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Recommendation

---

## Summary

The v0.2.0 spec requires that "adding a new function requires adding one entry to the table, not modifying the parser." This document proposes a concrete design for that table, addresses where constants live, and confirms how the evaluator dispatches through it.

---

## 1. Table Entry Struct

### Proposed Definition (Python dataclass)

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class FunctionEntry:
    name: str                          # lookup key, e.g. "sqrt"
    arity: int                         # expected argument count (-1 = variadic, not used here)
    fn: Callable[..., float]           # wrapped implementation
    domain_check: Optional[Callable[..., bool]] = None  # None = no restriction
```

**Fields rationale:**

| Field | Type | Purpose |
|-------|------|---------|
| `name` | `str` | Lookup key; matches the identifier scanned by the lexer |
| `arity` | `int` | Validated at call site before `fn` is invoked; drives the arity-mismatch error |
| `fn` | `Callable[..., float]` | Direct function pointer; called with evaluated arguments |
| `domain_check` | `Optional[Callable[..., bool]]` | Pre-call predicate; `None` means no restriction |

**Domain-check strategy:** A predicate field on the entry (option A) is preferred over inlining checks in a wrapper (option B) or relying on errno/NaN post-call (option C):

- Option A (predicate field): domain check is explicit, testable, and separated from the math call. Adding `log(x)` requires one entry with `domain_check=lambda x: x > 0`. The error message is always `DomainError`, consistent with the spec.
- Option B (wrapper): moves the check into a closure inside the table initialiser. This works but makes the table harder to read—the domain constraint is hidden.
- Option C (errno/NaN): relies on CPython's `math` module raising `ValueError` for out-of-domain inputs (e.g. `math.sqrt(-1)` raises `ValueError`). This actually works well in Python since `math` already raises `ValueError` for domain errors. However it conflates math-library exceptions with our own error taxonomy and produces a different error type depending on the platform.

**Recommendation:** Use the predicate field for `sqrt` and `log` (the only two functions with domain constraints in v0.2.0). For all others, `domain_check=None`.

### Concrete table (v0.2.0)

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
```

Adding a new function in a future version requires exactly one new `FunctionEntry` line. The parser is not touched.

---

## 2. Constants: Separate Dict (Not Function Table)

### Decision: `CONSTANT_TABLE: dict[str, float]`

```python
CONSTANT_TABLE: dict[str, float] = {
    "pi": math.pi,
    "e":  math.e,
}
```

**Why not arity-0 entries in `FUNCTION_TABLE`?**

- The parser distinguishes function calls (`name(...)`) from bare names (`pi`). An arity-0 function would require either (a) parsing `pi()` with mandatory empty parens, which the spec does not show, or (b) special-casing arity-0 during parsing to suppress the `(` requirement — that special case *is* a parser modification, violating the spec's extensibility constraint.
- The spec success criteria show `calc 'pi'` (no parens), confirming constants are bare identifiers.

**Why not literals emitted by the lexer?**

- Emitting numeric tokens for `pi` and `e` in the lexer hard-codes them at the token level. Future user-defined variables (`x = 5`) would also need to live in some runtime binding, not in the lexer. Treating constants as named bindings now makes the lookup mechanism available for variables later.

**How this supports future user-defined variables:**

The evaluator will carry a `namespace: dict[str, float]` (initially seeded from `CONSTANT_TABLE`). When `x = 5` is added in a future version, the assignment simply inserts into the same dict. The lookup path (`namespace[name]`) does not change. This is the same "environment" pattern used by most expression evaluators.

---

## 3. Lookup Strategy

### Decision: `dict` (hash map), O(1)

Build two separate `dict` structures at module load time:

```python
_FUNC_BY_NAME: dict[str, FunctionEntry] = {e.name: e for e in FUNCTION_TABLE}
_CONST_BY_NAME: dict[str, float] = CONSTANT_TABLE
```

**Alternatives considered:**

| Strategy | Complexity | Notes |
|----------|------------|-------|
| Linear scan | O(n) | Acceptable for ≤ 20 entries; simple but unnecessary given Python dicts |
| `dict` (hash map) | O(1) amortised | Natural Python structure; zero extra code |
| Sorted array + `bisect` | O(log n) | More code, no benefit at this scale |

Linear scan over a list of 12 entries would complete in nanoseconds; the choice is not performance-critical. A `dict` is still preferred because it matches how `CONSTANT_TABLE` is naturally written and makes "unknown function" detection a single `name in _FUNC_BY_NAME` test.

---

## 4. Evaluator Dispatch

### Decision: Direct function pointer call via table entry

The evaluator will gain a new AST node type:

```python
@dataclass
class FunctionCall:
    name: str
    args: list[ASTNode]
```

The evaluator handles it as:

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

No `switch`/`if-elif` dispatch on function name. The evaluator does not know about `sqrt` or `log` individually; it only knows `FunctionEntry`. This satisfies the spec constraint.

---

## 5. Existing Symbol Lookup in v0.1.x

The current evaluator (`src/calc/evaluator.py`) has no symbol lookup mechanism. It dispatches only on `isinstance(node, ...)` for `Number`, `UnaryOp`, and `BinaryOp`. Parenthesized grouping is handled entirely by the parser and produces no special AST node — the inner expression is simply the child node.

**Conclusion:** A new lookup layer is needed. The design above introduces it as two module-level dicts (`_FUNC_BY_NAME`, `CONSTANT_TABLE`). The evaluator receives a `FunctionCall` node and resolves it through `_FUNC_BY_NAME`. Named constants are resolved through `CONSTANT_TABLE` in a new `Name` node branch:

```python
@dataclass
class Name:
    identifier: str

# In evaluator:
if isinstance(node, Name):
    if node.identifier in CONSTANT_TABLE:
        return CONSTANT_TABLE[node.identifier]
    raise UnknownIdentifier(node.identifier)
```

This `Name` branch is the stub for future user-defined variables: when `x = 5` is added, `evaluate` checks an environment dict first, then falls back to `CONSTANT_TABLE`.

---

## Acceptance Criteria — Responses

### Concrete struct definition

```python
@dataclass(frozen=True)
class FunctionEntry:
    name: str
    arity: int
    fn: Callable[..., float]
    domain_check: Optional[Callable[..., bool]] = None
```

Fields: `name` (str), `arity` (int), `fn` (function pointer), `domain_check` (optional predicate).

### Where constants live

Separate `CONSTANT_TABLE: dict[str, float]`. Constants are resolved via a `Name` AST node in the evaluator — the same lookup mechanism that will serve user-defined variables. This avoids arity-0 function entries (which would force parser changes) and avoids lexer-level literals (which cannot be extended to runtime bindings).

### Lookup strategy and complexity

`dict` hash map; O(1) amortised. Built once at module load from `FUNCTION_TABLE`. Acceptable and idiomatic for the ≤ 20-entry scale of this project.

### Domain error detection

A `domain_check` predicate on `FunctionEntry` is evaluated before `fn` is called. If it returns `False`, `DomainError` is raised. `domain_check=None` means unconditionally safe. For v0.2.0 only `sqrt` and `log` have non-`None` predicates.

---

## Follow-up Issues

- Add `FunctionCall` and `Name` AST node types to `parser.py` (parser extension issue)
- Add `UnknownFunction`, `WrongArity`, `DomainError`, `UnknownIdentifier` to `errors.py` (error taxonomy issue)
- Implement `FUNCTION_TABLE` and `CONSTANT_TABLE` in a new `src/calc/functions.py` module
- Update `evaluator.py` to handle `FunctionCall` and `Name` nodes
