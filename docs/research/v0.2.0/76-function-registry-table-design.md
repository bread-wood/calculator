# Research: Function Registry Table Design and Arity Enforcement

**Issue:** #76
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Recommendation

---

## Summary

The v0.2.0 spec mandates: "adding a new function requires adding one entry to the table, not modifying the parser." This document consolidates prior research (#39, #54, #56) into a definitive table schema, resolves the constants storage question, and confirms that the design does not foreclose future user-defined variables.

Prior research has already established detailed recommendations that are directly applicable. This document synthesises those findings into a single authoritative reference.

---

## 1. Table Schema

### Recommended: `FunctionEntry` frozen dataclass

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class FunctionEntry:
    name: str                                         # lookup key; matches lexer IDENT token
    arity: int                                        # expected argument count
    fn: Callable[..., float]                          # implementation pointer
    domain_check: Optional[Callable[..., bool]] = None  # None = unrestricted
```

**Field summary:**

| Field | Type | Purpose |
|-------|------|---------|
| `name` | `str` | Primary lookup key; must match the exact string scanned by the lexer |
| `arity` | `int` | Validated by the evaluator before `fn` is called; drives `WrongArity` error |
| `fn` | `Callable[..., float]` | Direct function reference; called with already-evaluated float arguments |
| `domain_check` | `Optional[Callable[..., bool]]` | Pre-call predicate; `None` means no domain restriction |

**Why a frozen dataclass rather than a plain tuple?**

A `dict[str, tuple[int, Callable]]` would be the minimal representation, but the `domain_check` field gives three concrete benefits:

1. Domain constraints are co-located with the function they govern, not scattered across the evaluator.
2. The field is independently unit-testable: `entry.domain_check(-1)` can be asserted in isolation.
3. A reader can inspect the table to understand all restrictions without reading evaluator logic.

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

# Built once at module load; O(1) lookup
_FUNC_BY_NAME: dict[str, FunctionEntry] = {e.name: e for e in FUNCTION_TABLE}
```

Single-arg and two-arg functions live in the **same table** with an `arity` field distinguishing them (see §2). Adding a new function requires exactly one new `FunctionEntry` line.

---

## 2. Single Table vs. Separate Tables

**Decision: one table with an `arity` field.**

| Approach | Pros | Cons |
|----------|------|------|
| Single table + `arity` field | One lookup, extensible to N-arg functions, trivial to iterate | Runtime arity check (negligible cost) |
| Separate unary/binary tables | No runtime dispatch for arity | Two lookups, parallel maintenance, forecloses variadic or 3-arg functions |

A single table indexed by name supports mixed arities uniformly. The evaluator validates `len(node.args) != entry.arity` after the single lookup. There is no case where a function name is valid at one arity and invalid at another, so a single lookup is always sufficient.

---

## 3. Constants Storage

**Decision: separate `_DEFAULT_ENV: dict[str, float]` in the evaluator; do NOT put constants in the function table.**

### Options considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **(a) Separate constants dict** | `_DEFAULT_ENV = {"pi": math.pi, "e": math.e}` | ✓ Recommended |
| **(b) Same table, arity=0** | `FunctionEntry("pi", 0, lambda: math.pi)` | ✗ Rejected |
| **(c) Zero-arg thunk** | Same as (b) but with explicit `()` call syntax | ✗ Rejected |

**Why (a)?**

The grammar already distinguishes bare `IDENT` (→ `Name` AST node) from `IDENT LPAREN` (→ `FunctionCall` AST node). Constants are accessed as bare identifiers (`pi`, `e`), not as calls (`pi()`). Putting them in the function table would require the evaluator to synthesise a zero-argument call for every bare identifier access, which is artificial and inconsistent with the grammar.

A separate `dict[str, float]` maps directly to the `Name` node evaluation path:

```python
_DEFAULT_ENV: dict[str, float] = {
    "pi": math.pi,
    "e":  math.e,
}
```

This is exactly the same dict that future user variables (`x = 5`) will populate. The `Name` node lookup path serves both constants today and variables tomorrow with zero changes.

**Why not (b) or (c)?**

Option (b) with `arity=0` requires the evaluator to treat zero-arg entries specially (they cannot accept arguments from the AST, which represents them as `Name` not `FunctionCall`). Option (c) requires users to write `pi()` — inconsistent with the spec's success criteria which show bare `pi`.

---

## 4. Dispatch Code and Error Path

### Lookup and evaluation

```python
if isinstance(node, FunctionCall):
    entry = _FUNC_BY_NAME.get(node.name)
    if entry is None:
        raise UnknownFunction(node.name)           # error: unknown function: <name>
    if len(node.args) != entry.arity:
        raise WrongArity(node.name, entry.arity)   # error: wrong number of arguments: <name> expects <N>
    evaluated_args = [evaluate(arg, env) for arg in node.args]
    if entry.domain_check is not None and not entry.domain_check(*evaluated_args):
        raise DomainError()                        # error: domain error
    try:
        result = entry.fn(*evaluated_args)
    except OverflowError:
        raise Overflow()                           # math.exp(large) raises OverflowError, not returning inf
    _check_overflow(result)                        # catches functions returning inf/NaN without raising
    return result

if isinstance(node, Name):
    value = env.get(node.id)
    if value is None:
        raise UnknownName(node.id)                 # error: unknown name: <name>
    return value
```

**Error path for unknown function:** `_FUNC_BY_NAME.get(node.name)` returns `None` when the name is absent. The `if entry is None` guard immediately raises `UnknownFunction(node.name)`, which maps to the message `error: unknown function: <name>`. This is never a crash or a `KeyError`.

### New error classes required

```python
class DomainError(CalcError):     # error: domain error
class UnknownFunction(CalcError): # error: unknown function: <name>  (parameterised)
class WrongArity(CalcError):      # error: wrong number of arguments: <name> expects <N>  (parameterised)
class UnknownName(CalcError):     # error: unknown name: <name>  (parameterised)
```

---

## 5. Variable-Namespace Extensibility

**The function/constant registry does not collide with and does not prevent a future user-variable table.**

Three structural properties guarantee this:

1. **Grammar-enforced separation.** The parser produces `FunctionCall` nodes for `name(args)` syntax and `Name` nodes for bare `name` syntax. These are dispatched through separate code paths in the evaluator. A user variable `x` will always produce `Name("x")`; it will never interfere with `_FUNC_BY_NAME`.

2. **Independent data structures.** `_FUNC_BY_NAME` (function registry) and `_DEFAULT_ENV` (constants/variables dict) are completely separate objects. Adding user variables means mutating (or replacing) the `env` dict; it cannot affect `_FUNC_BY_NAME`, and vice versa.

3. **`evaluate()` signature supports runtime `env` injection.** The evaluator signature is:

   ```python
   def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
       if env is None:
           env = _DEFAULT_ENV
   ```

   A future REPL or multi-statement runner constructs its own `user_env = dict(_DEFAULT_ENV)` (copying constants), then calls `evaluate(node, user_env)` for each expression. Assignment nodes update `user_env` directly. The function registry is never touched. All existing call sites (`evaluate(node)`) continue to work unchanged.

**No parser changes are required to add variables.** The `IDENT` token type and the `Name` AST node already exist for constants; variables reuse both.

---

## 6. Summary of Decisions

| Question | Decision |
|----------|----------|
| **Table entry schema** | `FunctionEntry(name, arity, fn, domain_check)` frozen dataclass |
| **Single vs. separate tables** | Single table; `arity` field distinguishes unary/binary |
| **Constants storage** | Separate `_DEFAULT_ENV: dict[str, float]`; NOT in the function table |
| **Dispatch lookup** | `dict[str, FunctionEntry]` built at module load; `O(1)` by name |
| **Unknown function error** | `UnknownFunction(name)` → `error: unknown function: <name>`; never a crash |
| **Variable extensibility** | Confirmed: function table and `env` dict are fully independent; future `x=5` requires no parser change |

---

## Follow-up Issues

- Implement `FunctionEntry` dataclass and `FUNCTION_TABLE` in `src/calc/functions.py`
- Add `IDENT` and `COMMA` token types to the lexer; add `Name` and `FunctionCall` AST nodes to the parser
- Extend `_parse_primary()` with one-token look-ahead for `IDENT (` vs bare `IDENT`
- Add `DomainError`, `UnknownFunction`, `WrongArity`, `UnknownName` to `errors.py`
- Update `evaluator.py` to dispatch `Name` and `FunctionCall` nodes; add `_DEFAULT_ENV`
