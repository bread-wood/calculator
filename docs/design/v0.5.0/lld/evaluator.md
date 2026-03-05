# Low-Level Design — Evaluator Module (v0.5.0)

**Module:** `evaluator`
**File:** `src/calc/evaluator.py`
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

Walk the AST recursively and produce a `float` result. Maintain mutable variable and
function environments across statement execution. Enforce scoping, arity, domain,
constant-reassignment, duplicate-function, and forward-reference constraints. Expose
built-in constant values for use in the plot path.

The evaluator is shared by both the legacy expression pipeline and the new `plot`
subcommand. No evaluator changes are required for v0.5.0 beyond exposing
`_CONSTANTS_VALUES` (already present) and ensuring the module-level API contract is
documented precisely.

---

## 2. Data Structures

### 2.1 `FunctionEntry` (frozen dataclass)

```python
@dataclass(frozen=True)
class FunctionEntry:
    name: str
    arity: int
    fn: Callable[..., float]
    domain_check: Callable[..., bool] | None = None
```

Internal to the module. Each built-in function is represented by one `FunctionEntry`.
`domain_check` is called with the already-evaluated arguments before `fn` is invoked;
if it returns `False`, `DomainError` is raised.

### 2.2 `UserFunction` (frozen dataclass)

```python
@dataclass(frozen=True)
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode
    available_fns: dict[str, "UserFunction"]
```

Stored in `fn_env` by `execute_statement`. The `available_fns` snapshot captures the
set of user-defined functions that were in scope **at definition time**, enforcing the
forward-reference prohibition structurally (a function body cannot call functions
defined after it).

### 2.3 `_FUNCTION_TABLE: dict[str, FunctionEntry]`

Module-level mapping from function name to `FunctionEntry`. Built once at import time
from `_FUNCTION_LIST`. Read-only at runtime.

Built-in functions:

| Name | Arity | Domain check |
|------|-------|-------------|
| `sqrt` | 1 | `x >= 0` |
| `abs` | 1 | none |
| `floor` | 1 | none |
| `ceil` | 1 | none |
| `round` | 1 | none (half-away-from-zero) |
| `sin` | 1 | none |
| `cos` | 1 | none |
| `tan` | 1 | none |
| `log` | 1 | `x > 0` |
| `exp` | 1 | none |
| `pow` | 2 | none |
| `atan2` | 2 | none |

### 2.4 Constant tables

```python
_CONSTANTS_VALUES: dict[str, float] = {"pi": math.pi, "e": math.e}
_CONSTANTS: frozenset[str] = frozenset(_CONSTANTS_VALUES)
_DEFAULT_ENV: MappingProxyType = MappingProxyType(dict(_CONSTANTS_VALUES))
```

- `_CONSTANTS_VALUES` — exported to `plotter.py` so that named constants are available
  in plotted expressions without the plot module depending on the full evaluator state.
- `_CONSTANTS` — membership check in `execute_statement` to block reassignment.
- `_DEFAULT_ENV` — immutable proxy used as default `env` in headless `evaluate` calls
  (e.g., single-expression evaluation without a CLI env dict).

---

## 3. Public API

### 3.1 `evaluate(node, env, fn_env) → float`

```python
def evaluate(
    node: ASTNode,
    env: dict[str, float] | None = None,
    fn_env: dict[str, UserFunction] | None = None,
) -> float:
```

Recursively evaluates an AST node.

- If `env` is `None`, uses `_DEFAULT_ENV` (read-only).
- If `fn_env` is `None`, uses `{}`.
- Raises `CalcError` subclasses for all domain/runtime errors.
- Does **not** mutate `env` or `fn_env`.

**Dispatch table:**

| Node type | Action |
|-----------|--------|
| `Number` | Return `node.value` |
| `UnaryOp('-')` | Evaluate operand, negate, check overflow |
| `BinaryOp('+','-','*','/')` | Evaluate both sides, apply op, check overflow; `/` raises `DivisionByZero` when right == 0.0 |
| `Name` | Look up `node.name` in `env`; raise `UndefinedVariable` if absent |
| `Call` | Check `fn_env` first, then `_FUNCTION_TABLE`; raise `UnknownFunction` if absent; check arity; run domain check; call `fn`; catch `OverflowError` → `Overflow` |

### 3.2 `execute_statement(stmt, env, fn_env) → float | None`

```python
def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction] | None = None,
) -> float | None:
```

Dispatches on `stmt` type:

- `FunctionDef` — validates body calls, stores `UserFunction` in `fn_env`, returns `None`.
- `Assignment` — guards against constant reassignment, evaluates RHS, stores in `env`, returns the value.
- Any `ASTNode` — delegates to `evaluate(stmt, env, fn_env)`, returns the value.

Mutates `env` (for assignments) and `fn_env` (for function definitions).

### 3.3 `format_result(value: float) → str`

```python
def format_result(value: float) -> str:
```

- If `value == int(value)` and not `isinf(value)`: return `str(int(value))` (no decimal point).
- Otherwise: return `str(value)` (Python default float representation).

### 3.4 Module-level exports consumed by other modules

| Symbol | Consumer | Purpose |
|--------|----------|---------|
| `evaluate` | `plotter.py` | Sample expression per x value |
| `_CONSTANTS_VALUES` | `plotter.py` | Seed env with `pi`/`e` for plot expressions |
| `UserFunction` | `__main__.py` | Type annotation in legacy eval loop |
| `execute_statement` | `__main__.py` | Legacy eval loop |
| `format_result` | `__main__.py` | Legacy result formatting |

---

## 4. Key Algorithms

### 4.1 Recursive AST evaluation

Standard post-order tree walk. Each call to `evaluate` returns a single `float`. No
memoisation; no iteration limit. The AST depth is bounded by expression complexity
(parsing enforces this via stack depth; no cycles are possible in an immutable AST).

### 4.2 Overflow detection

```python
def _check_overflow(result: float) -> None:
    if math.isinf(result) or math.isnan(result):
        raise Overflow()
```

Called after every arithmetic operation (unary negate, binary `+/-/*`). Division
result is not separately checked because IEEE 754 division of finite values with
non-zero divisor cannot produce `inf`; only negation and addition/multiplication
can overflow finite inputs. `OverflowError` from `math` functions is caught at the
call site and re-raised as `Overflow`.

### 4.3 User function call (`_call_user_fn`)

```python
def _call_user_fn(uf, args, env, fn_env):
    # 1. Check arity
    if len(args) != len(uf.params):
        raise WrongArity(uf.name, len(uf.params))
    # 2. Evaluate arguments in the *caller's* environment
    evaled_args = [evaluate(a, env, fn_env) for a in args]
    # 3. Build function body environment: constants + bound params
    body_env = dict(_CONSTANTS_VALUES)
    body_env.update(zip(uf.params, evaled_args))
    # 4. Evaluate body in the *definition-time* fn_env snapshot
    return evaluate(uf.body, body_env, uf.available_fns)
```

Key scoping decisions:
- Arguments are evaluated in the **caller's** `env`/`fn_env`.
- The body sees only `_CONSTANTS_VALUES` plus the bound parameters — not the caller's
  variables. This prevents accidental capture of caller-scope variables.
- The body's `fn_env` is `uf.available_fns` (the snapshot at definition time), not the
  current `fn_env`. This enforces the forward-reference prohibition.

### 4.4 Forward-reference validation (`_validate_body_calls`)

Called at `FunctionDef` time, before storing the function. Walks the body AST and for
every `Call` node checks that the called name is either in `_FUNCTION_TABLE` or in the
currently-defined `fn_env`. Raises `UnknownFunction` if a name is not resolvable.

This is a static check (no evaluation); it does not validate variable names in the
body (those are checked at call time).

### 4.5 Half-away-from-zero rounding

```python
def _round_half_away(x: float) -> float:
    return float(math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5))
```

Python's built-in `round()` uses banker's rounding (round-half-to-even). The
calculator spec requires half-away-from-zero, so a custom helper is registered as
the `round` built-in function.

---

## 5. Error Handling

All errors are `CalcError` subclasses. The evaluator raises but never catches them
(except to re-wrap `OverflowError`). The caller is responsible for handling.

### 5.1 Errors raised by `evaluate`

| Condition | Error class | Raised in |
|-----------|-------------|-----------|
| Variable not in `env` | `UndefinedVariable(name)` | `Name` branch |
| Function not in `fn_env` or `_FUNCTION_TABLE` | `UnknownFunction(name)` | `Call` branch |
| Wrong argument count for built-in | `WrongArity(name, expected)` | `Call` branch |
| Wrong argument count for user function | `WrongArity(name, expected)` | `_call_user_fn` |
| Domain check fails (e.g., `sqrt(-1)`, `log(0)`) | `DomainError()` | `Call` branch |
| Arithmetic overflow (`isinf`/`isnan`) | `Overflow()` | `_check_overflow` |
| Division by zero | `DivisionByZero()` | `BinaryOp('/')` branch |
| `math` function raises `OverflowError` | `Overflow()` | `Call` branch |

### 5.2 Errors raised by `execute_statement`

| Condition | Error class |
|-----------|-------------|
| Assigning to `pi` or `e` | `ConstantReassignment(name)` |
| Redefining a built-in function name | `CannotRedefineBuiltin(name)` |
| Defining a function that already exists in `fn_env` | `FunctionAlreadyDefined(name)` |
| Body references unknown function | `UnknownFunction(name)` (via `_validate_body_calls`) |

### 5.3 Plot-path error wrapping

On the `plot` path, `plotter.py` calls `evaluate(ast, {"x": xi, **_CONSTANTS_VALUES})`
per sample point. Any `CalcError` raised for a given sample is caught by `plotter.py`
and the sample is marked `None` (gap). The evaluator is not aware of the plot context.

If the expression contains a call to an undefined function, `UnknownFunction` propagates
out of the very first sample evaluation. `run_plot` in `__main__.py` catches it and
re-raises as `UndefinedFunction` (the spec-mandated format for the plot path). This
wrapping happens in the CLI, not in the evaluator.

---

## 6. No Changes Required for v0.5.0

The evaluator module as implemented in v0.4.x satisfies all v0.5.0 requirements:

1. `evaluate` already accepts an arbitrary `env` dict — the plotter passes
   `{"x": xi, **_CONSTANTS_VALUES}`.
2. `_CONSTANTS_VALUES` is already a module-level dict and can be imported by
   `plotter.py`.
3. All per-sample errors (`DivisionByZero`, `DomainError`, `Overflow`) are already
   `CalcError` subclasses — `plotter.py` catches `CalcError` generically.
4. `UnknownFunction` propagates out of `plotter.sample_expression` unchanged; the
   CLI wraps it in `UndefinedFunction`.

No source changes are made to `src/calc/evaluator.py` in this milestone.

---

## 7. Test Strategy

The evaluator test file (`tests/test_evaluator.py`) covers all v0.1.x–v0.4.x
behaviour. No new test cases are required in v0.5.0 because the evaluator itself is
unchanged.

The plot path exercises the evaluator indirectly through `tests/test_plotter.py` and
`tests/test_plot.py`. Integration tests in those files are the primary verification
that the evaluator integrates correctly with the plotter.

### 7.1 Existing test coverage (must remain passing)

| Category | Representative cases |
|----------|---------------------|
| Arithmetic | `1+2`, `3*4`, `10/2`, `-5`, `2^3` (not applicable; no `^` in grammar) |
| Division by zero | `1/0` → `DivisionByZero` |
| Overflow | `exp(1000)` → `Overflow` |
| Domain | `sqrt(-1)` → `DomainError`; `log(0)` → `DomainError` |
| Constants | `pi` → `math.pi`; `e` → `math.e` |
| Constant reassignment | `pi = 3` → `ConstantReassignment` |
| User functions | Define and call; wrong arity → `WrongArity` |
| Forward reference | Function body calling undefined function → `UnknownFunction` |
| Duplicate function | Redefine same function → `FunctionAlreadyDefined` |
| Redefine built-in | `def sin(x) = x` → `CannotRedefineBuiltin` |
| `format_result` | Integers shown without decimal; floats shown as-is |
| `round` | Half-away-from-zero: `round(2.5)` → `3`, `round(-2.5)` → `-3` |

### 7.2 Regression guard

All existing `tests/test_evaluator.py` tests must pass with zero modifications. The
CI gate (`make test`) is the enforcement mechanism.

### 7.3 Plot-path evaluator coverage (in `tests/test_plotter.py`)

| Scenario | Verification |
|----------|-------------|
| `f(x) = x` over `[-1, 1]` | All samples valid; no gaps |
| `f(x) = 1/x` near 0 | Sample at x=0 marked `None` (gap) |
| `f(x) = sqrt(x)` over `[-1, 1]` | Negative-x samples marked `None` |
| `f(x) = log(x)` over `[-1, 1]` | Non-positive-x samples marked `None` |
| `f(x) = pi` | Constant expression evaluates correctly using `_CONSTANTS_VALUES` |
| `f(x) = undefined_fn(x)` | `UnknownFunction` propagates; CLI wraps as `UndefinedFunction` |

---

## 8. Module Interface Summary

```
src/calc/evaluator.py
├── FunctionEntry          (frozen dataclass, internal)
├── UserFunction           (frozen dataclass, public)
├── _FUNCTION_LIST         (list[FunctionEntry], internal)
├── _FUNCTION_TABLE        (dict[str, FunctionEntry], internal)
├── _CONSTANTS_VALUES      (dict[str, float], exported to plotter)
├── _CONSTANTS             (frozenset[str], internal)
├── _DEFAULT_ENV           (MappingProxyType, internal default)
├── evaluate()             (public, called by plotter and __main__)
├── execute_statement()    (public, called by __main__ legacy path)
├── format_result()        (public, called by __main__ legacy path)
├── _call_user_fn()        (private helper)
├── _validate_body_calls() (private helper)
├── _check_overflow()      (private helper)
└── _round_half_away()     (private helper)
```

**Dependencies:**
- `calc.parser` — AST node types
- `calc.errors` — all `CalcError` subclasses used
- `math` — arithmetic functions and constants
- `dataclasses`, `types`, `typing` — stdlib only

**Dependents (v0.5.0):**
- `calc.plotter` — imports `evaluate`, `_CONSTANTS_VALUES`, `CalcError`
- `calc.__main__` — imports `evaluate`, `execute_statement`, `format_result`,
  `UserFunction`, `_DEFAULT_ENV`
