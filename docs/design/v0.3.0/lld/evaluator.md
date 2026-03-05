# Low-Level Design — Evaluator Module (v0.3.0)

**Module:** `evaluator`
**File:** `src/calc/evaluator.py`
**Milestone:** v0.3.0 (Variables)
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

The evaluator walks a typed AST produced by the parser and computes a numeric `float` result. In v0.3.0 it gains two additional responsibilities: maintaining a mutable variable environment that accumulates user-defined variable bindings across statements, and enforcing read-only protection for the built-in constants `pi` and `e`. The existing `evaluate()` function remains a **pure** expression evaluator; a new top-level function `execute_statement()` handles the state-mutating assignment case and dispatches to `evaluate()` for expression statements.

**Scope boundary:** The evaluator does not parse source text, tokenise, format output, manage CLI arguments, or set process exit codes. It does not know how many statements exist in a program — that is the caller's (`__main__.py`) concern. It does not persist state between invocations; all variable bindings live in the `env` dict that the caller creates and passes in.

---

## 2. Public Interface

### 2.1 `evaluate(node, env) → float`

```python
def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
```

Recursively evaluates an expression-level AST node and returns its `float` value. The `env` argument carries the current variable bindings (including built-in constants).

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `node` | `ASTNode` | Expression node to evaluate (`Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call`) |
| `env` | `dict[str, float] \| None` | Variable environment. When `None`, a fresh copy of `_DEFAULT_ENV` is used. |

**Returns:** `float` — the numeric value of the expression.

**Raises:** See §7.

**Purity constraint:** `evaluate()` never writes to `env`. It only reads from it (via `env[node.name]` in the `Name` case). This invariant makes `evaluate()` safe to call from any context, including future read-only function-body scopes in v0.4.0.

**`env=None` behaviour:** When called without an explicit `env` (e.g., in tests or single-expression use), the function creates a fresh `dict(_DEFAULT_ENV)` copy. This copy contains `pi` and `e` and is discarded after the call. Because `_DEFAULT_ENV` is a `MappingProxyType`, no write can accidentally corrupt it (research #114 Q4).

### 2.2 `execute_statement(stmt, env) → float | None`

```python
def execute_statement(stmt: Statement, env: dict[str, float]) -> float | None:
```

Executes a single statement. For `Assignment` statements, evaluates the right-hand side, guards against constant reassignment, writes the result to `env`, and returns the assigned value. For expression statements (`ASTNode`), delegates to `evaluate()` and returns the result.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `stmt` | `Statement` | Either an `Assignment` or any `ASTNode` (expression statement) |
| `env` | `dict[str, float]` | Mutable variable environment; **must not be `None`**. The caller constructs this dict before the first statement and passes the same dict to each subsequent call, allowing variables to accumulate. |

**Returns:** `float | None`

- For an `Assignment` statement: the assigned value as `float`. Callers use the return value to determine the "last statement result" for display.
- For an expression statement (`ASTNode`): the evaluated `float`.
- In practice returns `float` for all valid inputs in v0.3.0. The `| None` return type is present to accommodate a hypothetical future statement type that has no value (e.g., a `print` statement); no current code path returns `None`.

**Raises:** `ConstantReassignment` if the assignment target is a member of `_CONSTANTS`. See §7.

**Resolution of HLD open question #2:** `execute_statement` is a **module-level function**, not a method. The evaluator has no instance state; all state flows through `env`. A free function keeps the public API simple and avoids forcing callers to construct an evaluator object. The last-statement-is-assignment case returns the assigned value (not `None`) so that `__main__.py` can print the result without a separate lookup into `env`.

### 2.3 `format_result(value) → str`

```python
def format_result(value: float) -> str:
```

Unchanged from v0.2.0. Formats a `float` for user-visible output: returns the integer representation (no decimal point) when `value == int(value)` and the value is finite; returns the default `str(float)` representation otherwise.

### 2.4 Module-level constants

```python
_CONSTANTS: frozenset[str]
_DEFAULT_ENV: types.MappingProxyType
```

`_CONSTANTS` is a `frozenset[str]` of all read-only built-in names. In v0.3.0: `frozenset({"pi", "e"})`. It is derived from `_DEFAULT_ENV` so the two cannot diverge.

`_DEFAULT_ENV` is a `types.MappingProxyType` wrapping `{"pi": math.pi, "e": math.e}`. It is read-only at the Python level; any attempt to write to it raises `TypeError` immediately (research #114 Q4).

Both constants are **private** (underscore-prefixed) but are importable for use in `execute_statement` and for tests that verify constant-protection behaviour.

---

## 3. Data Structures

### 3.1 Variable Environment (`env`)

```python
env: dict[str, float]
```

A plain Python `dict` mapping variable names (strings) to their current `float` values. The caller (`__main__.py`) constructs a fresh env at the start of each invocation:

```python
env = dict(_DEFAULT_ENV)    # {"pi": 3.141592..., "e": 2.718281...}
```

This pre-populates the env with built-in constants so that `evaluate()` can resolve `pi` and `e` via the same `env[node.name]` lookup path used for user variables. No special-case lookup for constants inside `evaluate()` is needed.

**Invariants:**

| Invariant | Enforced by |
|---|---|
| `_DEFAULT_ENV` is never mutated | `MappingProxyType`; runtime `TypeError` if attempted |
| User variables never bleed between invocations | Fresh `dict(_DEFAULT_ENV)` per call in `evaluate(env=None)` path; caller-constructed fresh dict for multi-statement programs |
| `_CONSTANTS` names cannot be overwritten | `execute_statement()` checks before writing |
| `env` values are always `float` | `evaluate()` always returns `float`; the only write site is `execute_statement()` |

### 3.2 `_CONSTANTS`

```python
_CONSTANTS: frozenset[str] = frozenset(_DEFAULT_ENV)
```

Derived from `_DEFAULT_ENV` at module load time, so there is a single source of truth. Adding a new constant requires only one edit: add it to the `_DEFAULT_ENV` initialiser dict; `_CONSTANTS` updates automatically.

### 3.3 `FunctionEntry` and `_FUNCTION_TABLE` (unchanged)

`FunctionEntry` is a frozen dataclass carrying `(name, arity, fn, domain_check)` for each built-in function. `_FUNCTION_TABLE` is a module-level `dict[str, FunctionEntry]`. Both are unchanged from v0.2.0 and are not described further here.

---

## 4. Key Algorithms and Logic

### 4.1 `execute_statement` — Assignment Dispatch

```python
def execute_statement(stmt: Statement, env: dict[str, float]) -> float | None:
    if isinstance(stmt, Assignment):
        if stmt.name in _CONSTANTS:
            raise ConstantReassignment(stmt.name)
        val = evaluate(stmt.value, env)
        env[stmt.name] = val
        return val
    return evaluate(stmt, env)
```

**Flow:**

```
execute_statement(stmt, env)
    │
    ├─ isinstance(stmt, Assignment)?
    │       YES:
    │       ├─ stmt.name in _CONSTANTS?
    │       │       YES → raise ConstantReassignment(stmt.name)  ← no mutation
    │       │
    │       ├─ val = evaluate(stmt.value, env)
    │       ├─ env[stmt.name] = val
    │       └─ return val
    │
    └─ NO (expression statement):
            return evaluate(stmt, env)
```

**Order of operations for Assignment:**
1. Constant guard runs **before** `evaluate()`. This means `pi = undefined_var` raises `ConstantReassignment`, not `UndefinedVariable`. This is intentional: rejecting the assignment target first gives the most actionable error.
2. `evaluate(stmt.value, env)` runs **before** `env[stmt.name] = val`. This means `x = x + 1` raises `UndefinedVariable` when `x` is not yet in `env` — the self-referential assignment is not silently initialised to a default.
3. The write `env[stmt.name] = val` happens only after both guards pass.

**Self-assignment (`x = x`):**  If `x` is already in `env`, `evaluate(Name("x"), env)` returns its current value, and `env["x"]` is overwritten with the same value. No special case needed.

### 4.2 `evaluate` — Expression Walker (unchanged from v0.2.0)

The `evaluate` dispatcher is structurally unchanged. The only modification is the `env=None` guard:

```python
# v0.2.0
if env is None:
    env = _DEFAULT_ENV          # aliased the singleton — latent mutation bug

# v0.3.0
if env is None:
    env = dict(_DEFAULT_ENV)    # fresh copy; aliasing eliminated
```

All existing `isinstance` dispatch arms (`Number`, `UnaryOp`, `BinaryOp`, `Name`, `Call`) are unchanged. The `Name` arm raises `UndefinedVariable` (renamed from `UnknownName`):

```python
if isinstance(node, Name):
    if node.name not in env:
        raise UndefinedVariable(node.name)
    return env[node.name]
```

### 4.3 v0.4.0 Forward Compatibility

The flat `dict[str, float]` env is the approved foundation for v0.4.0 function-parameter scoping (research #109). The design satisfies all three constraints that prevent a breaking rewrite:

1. User variables are never written into `_DEFAULT_ENV` (fresh copy per invocation).
2. `evaluate()`'s `env` parameter type is `dict[str, float] | None` — a `Scope` wrapper can be introduced in v0.4.0 via an `isinstance(env, dict)` shim without changing the public signature.
3. Constant protection lives in `execute_statement()` at the mutation site, not buried in the data structure, so it migrates cleanly if a `Scope` abstraction is introduced.

---

## 5. Internal Structure

### 5.1 File Layout (`src/calc/evaluator.py`)

```
imports
  import math
  import types
  from dataclasses import dataclass
  from typing import Callable
  from calc.parser import ASTNode, Assignment, Statement, Number, BinaryOp, UnaryOp, Name, Call
  from calc.errors import (
      DivisionByZero, Overflow, DomainError,
      UnknownFunction, WrongArity,
      UndefinedVariable, ConstantReassignment,
  )

private helpers
  _round_half_away(x: float) -> float    (unchanged)

dataclasses
  FunctionEntry                           (unchanged)

module-level constants
  _FUNCTION_LIST: list[FunctionEntry]     (unchanged)
  _FUNCTION_TABLE: dict[str, FunctionEntry]   (unchanged)
  _DEFAULT_ENV: MappingProxyType          (updated: now MappingProxyType)
  _CONSTANTS: frozenset[str]             (new v0.3.0)

public functions
  evaluate(node, env) -> float            (updated: env=None copies _DEFAULT_ENV)
  execute_statement(stmt, env) -> float | None  (new v0.3.0)
  format_result(value) -> str             (unchanged)

private helpers
  _check_overflow(result: float) -> None  (unchanged)
```

### 5.2 Import Changes

| Import | Change |
|---|---|
| `from calc.parser import ...` | Add `Assignment`, `Statement` to existing imports |
| `from calc.errors import ...` | Replace `UnknownName` with `UndefinedVariable`; add `ConstantReassignment` |
| `import types` | New — for `MappingProxyType` |

### 5.3 Private Helpers

| Helper | Change | Purpose |
|---|---|---|
| `_round_half_away(x)` | Unchanged | Half-away-from-zero rounding for `round()` built-in |
| `_check_overflow(result)` | Unchanged | Raises `Overflow` if result is infinite or NaN |

No new private helpers are introduced. `execute_statement` is concise enough to be self-contained.

---

## 6. Error Handling

### 6.1 Errors raised by this module

| Error | Function | Condition |
|---|---|---|
| `UndefinedVariable(name)` | `evaluate()` | A `Name` node's `name` is not a key in `env` |
| `ConstantReassignment(name)` | `execute_statement()` | Assignment target is in `_CONSTANTS` |
| `DivisionByZero()` | `evaluate()` | Right operand of `/` evaluates to `0.0` |
| `Overflow()` | `evaluate()` | Result of arithmetic is `inf` or `NaN` |
| `DomainError()` | `evaluate()` | Argument to a function fails its `domain_check` |
| `UnknownFunction(name)` | `evaluate()` | `Call.func` is not a key in `_FUNCTION_TABLE` |
| `WrongArity(name, expected)` | `evaluate()` | `len(Call.args)` ≠ `entry.arity` |

`UndefinedVariable` and `ConstantReassignment` are new in v0.3.0. All others are unchanged from v0.2.0.

### 6.2 Errors propagated from dependencies

`evaluate()` calls itself recursively and calls `entry.fn(*evaled_args)` for built-in functions. An `OverflowError` from the stdlib math function is caught and re-raised as `Overflow()`. All other exceptions propagate unchanged.

`execute_statement()` calls `evaluate()` and does not catch any of its errors; they propagate directly to the caller (`__main__.py`).

### 6.3 Non-errors / invariants

`TypeError` from `_DEFAULT_ENV[key] = value` (if attempted) is not a `CalcError` and is not caught. It indicates a programmer error (writing to the proxy directly) and should surface as an unhandled exception. This is intentional — it is a development-time guard, not a user-facing error.

---

## 7. Testing Strategy

Tests live in `tests/test_evaluator.py`.

### 7.1 Regression: existing tests

All v0.2.0 tests pass without modification **except** for the `eval_expr` helper, which calls `Parser(Lexer(s)).parse()`. In v0.3.0, `parse()` is replaced by `parse_program()` returning a `Program`; the helper must be updated:

```python
def eval_expr(s: str) -> float:
    from calc.lexer import Lexer
    from calc.parser import Parser
    prog = Parser(Lexer(s)).parse_program()
    return evaluate(prog.body[0])
```

No assertion logic changes. All existing parametrised tests (`test_evaluate`, `test_functions_and_constants`, `test_format_result`, `test_domain_error_sqrt`, etc.) remain valid.

### 7.2 New happy-path tests: `execute_statement`

| Test | Setup | Assertion |
|---|---|---|
| Single assignment | `env = dict(_DEFAULT_ENV)` | `execute_statement(Assignment("x", Number(5.0)), env)` returns `5.0` and `env["x"] == 5.0` |
| Variable reference after assignment | Assign `x=5`, then `execute_statement(BinaryOp("+", Name("x"), Number(1.0)), env)` | Returns `6.0` |
| Multi-statement env accumulation | Assign `x=5`, then assign `y=BinaryOp("*", Name("x"), Number(2.0))` | `env["y"] == 10.0` |
| Expression statement (no assignment) | `execute_statement(BinaryOp("+", Number(2.0), Number(3.0)), env)` | Returns `5.0`; `env` unchanged |
| Last statement is assignment | Assign `x=7`; return value of `execute_statement` | Returns `7.0` (not `None`) |
| Self-overwrite | `env["x"] = 3.0`; then assign `x=9.0` | `env["x"] == 9.0` |
| pi and e readable | `execute_statement(Name("pi"), env)` | Returns `math.pi` |

### 7.3 Constant protection tests

```python
def test_constant_reassignment_pi():
    env = dict(_DEFAULT_ENV)
    with pytest.raises(ConstantReassignment) as exc_info:
        execute_statement(Assignment("pi", Number(3.0)), env)
    assert exc_info.value.name == "pi"
    assert env["pi"] == math.pi   # env must be unchanged

def test_constant_reassignment_e():
    env = dict(_DEFAULT_ENV)
    with pytest.raises(ConstantReassignment):
        execute_statement(Assignment("e", Number(2.0)), env)
    assert env["e"] == math.e

def test_constant_reassignment_precedes_evaluation():
    # Guard fires before rhs is evaluated; UndefinedVariable must NOT be raised
    env = dict(_DEFAULT_ENV)
    with pytest.raises(ConstantReassignment):
        execute_statement(Assignment("pi", Name("undefined_var")), env)
```

The last test is the most important: it verifies that the guard in `execute_statement` fires **before** calling `evaluate(stmt.value, env)`, matching the intended order of operations (§4.1).

### 7.4 `UndefinedVariable` tests

```python
def test_undefined_variable_raises():
    env = dict(_DEFAULT_ENV)
    with pytest.raises(UndefinedVariable) as exc_info:
        evaluate(Name("x"), env)
    assert exc_info.value.name == "x"

def test_undefined_variable_after_assignment():
    # y is defined; z is not
    env = dict(_DEFAULT_ENV)
    execute_statement(Assignment("y", Number(1.0)), env)
    with pytest.raises(UndefinedVariable):
        evaluate(Name("z"), env)
```

### 7.5 `_DEFAULT_ENV` immutability test

```python
def test_default_env_is_immutable():
    import types
    from calc.evaluator import _DEFAULT_ENV
    assert isinstance(_DEFAULT_ENV, types.MappingProxyType)
    with pytest.raises(TypeError):
        _DEFAULT_ENV["x"] = 1.0
```

### 7.6 Fresh env isolation test

```python
def test_no_state_leaks_between_invocations():
    # First call assigns x via the env=None path (single expression)
    env1 = dict(_DEFAULT_ENV)
    execute_statement(Assignment("x", Number(42.0)), env1)
    # Second call should not see x
    env2 = dict(_DEFAULT_ENV)
    with pytest.raises(UndefinedVariable):
        evaluate(Name("x"), env2)
```

### 7.7 Integration-style tests (via `eval_expr`)

Full multi-statement programs are exercised in `tests/test_cli.py`. Evaluator-level integration tests (without subprocess) verify the pipeline up to `execute_statement`:

| Input (parsed) | Expected result |
|---|---|
| `x = 5; y = x * 2; y + 1` | `11.0` |
| `x = sqrt(9)` | `3.0` (also in `env`) |
| `pi * 2` | `2 * math.pi` |
| `x = 5; x` | last statement result = `5.0` |

### 7.8 What to mock

Nothing. The evaluator has no I/O and no external side effects. `_FUNCTION_TABLE` is a module-level constant; there is no need to mock it.

---

## 8. Dependencies

| Dependency | Direction | What is used |
|---|---|---|
| `src/calc/parser.py` | import | `ASTNode`, `Assignment`, `Statement`, `Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call` |
| `src/calc/errors.py` | import | `DivisionByZero`, `Overflow`, `DomainError`, `UnknownFunction`, `WrongArity`, `UndefinedVariable`, `ConstantReassignment` |
| `math` (stdlib) | import | `math.pi`, `math.e`, `math.floor`, `math.ceil`, `math.isinf`, `math.isnan`, and the built-in function implementations |
| `types` (stdlib) | import | `types.MappingProxyType` for `_DEFAULT_ENV` |

`evaluator.py` is imported by `__main__.py` (which calls `execute_statement` and `format_result`) and by `tests/test_evaluator.py`. It does not import from `__main__.py` (no circular dependency).

---

## 9. Migration from v0.2.0

### Changes to `src/calc/evaluator.py`

| Item | v0.2.0 | v0.3.0 |
|---|---|---|
| `_DEFAULT_ENV` type | `dict[str, float]` | `types.MappingProxyType` |
| `evaluate()` `env=None` guard | `env = _DEFAULT_ENV` | `env = dict(_DEFAULT_ENV)` |
| `Name` node error | `raise UnknownName(node.name)` | `raise UndefinedVariable(node.name)` |
| `_CONSTANTS` | absent | `frozenset[str]` at module level |
| `execute_statement()` | absent | new public function |
| Import: `UnknownName` | present | removed |
| Import: `UndefinedVariable` | absent | added |
| Import: `ConstantReassignment` | absent | added |
| Import: `Assignment`, `Statement` | absent | added |
| Import: `types` | absent | added |

### Changes to `tests/test_evaluator.py`

| Change | Detail |
|---|---|
| `eval_expr` helper | Update `parse()` → `parse_program().body[0]` |
| Add `execute_statement` import | `from calc.evaluator import execute_statement` |
| Add `UndefinedVariable` import | `from calc.errors import UndefinedVariable` |
| Add `ConstantReassignment` import | `from calc.errors import ConstantReassignment` |
| New test functions | See §7.3–7.6 |
| Existing test functions | No assertion changes |

### Files that do NOT change (evaluator perspective)

`src/calc/lexer.py`, `src/calc/parser.py` (except adding `Assignment`/`Program`/`Statement` which are parser-LLD scope), `tests/test_lexer.py`, `tests/test_parser.py`.
