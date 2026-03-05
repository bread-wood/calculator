# Low-Level Design — Evaluator Module (v0.4.0)

**Module:** `evaluator` (`src/calc/evaluator.py`)
**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Draft
**Research inputs:** #154, #155, #156, #157, #159

---

## 1. Responsibility

The evaluator module:

- Walks the AST recursively and produces a `float` result.
- Maintains a mutable variable environment (`env: dict[str, float]`) and a
  separate mutable function environment (`fn_env: dict[str, UserFunction]`)
  across statement executions within a single program invocation.
- Stores and retrieves user-defined functions.
- Enforces: variable/constant scoping, arity, domain, constant-reassignment,
  duplicate-function, and forward-reference constraints.
- Detects arithmetic overflow.
- Formats the final numeric result as a string for stdout.

---

## 2. Data Structures

### 2.1 Module-level constants

```python
import math
from types import MappingProxyType

_CONSTANTS_VALUES: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}

# Single source of truth; both _CONSTANTS and _DEFAULT_ENV derive from it.
_CONSTANTS: frozenset[str] = frozenset(_CONSTANTS_VALUES)
_DEFAULT_ENV: MappingProxyType[str, float] = MappingProxyType(_CONSTANTS_VALUES)
```

`_CONSTANTS_VALUES` is the canonical dict of named constants. It is used:
- As the base for `_DEFAULT_ENV` (top-level evaluation environment).
- As the seed for `body_env` on every user-function call (§ 3.3).

`_DEFAULT_ENV` is a read-only proxy; the CLI copies it with `dict(_DEFAULT_ENV)`
to produce a mutable per-invocation environment.

### 2.2 `FunctionEntry` (built-in functions, unchanged)

```python
@dataclass
class FunctionEntry:
    fn: Callable[..., float]
    arity: int
    domain_check: Callable[[tuple[float, ...]], bool] | None = None
```

`_FUNCTION_TABLE: dict[str, FunctionEntry]` maps 12 built-in function names to
their `FunctionEntry`. This structure is unchanged from v0.3.x.

### 2.3 `UserFunction` (new in v0.4.0)

```python
@dataclass(frozen=True)
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode                              # parsed expression tree; NOT a Callable
    available_fns: dict[str, "UserFunction"]  # snapshot of fn_env at definition time
```

Key properties:

- **`body` is an `ASTNode`, never a `Callable`.**  Storing a callable would
  make the type non-serializable, violating the v0.4.0 spec constraint.
- **`available_fns` is a snapshot.** It is `dict(fn_env)` captured at the
  moment the `def` statement executes. This snapshot enforces the forward-
  reference prohibition structurally: the function being defined is not yet
  in `fn_env` when the snapshot is taken, so any self-call or call to a
  later-defined function is absent from the snapshot and will be rejected by
  the definition-time AST walk (§ 3.2).
- The dataclass is `frozen=True`, making instances hashable and preventing
  post-construction mutation.

---

## 3. Key Algorithms

### 3.1 `evaluate(node, env, fn_env) → float`

Signature:

```python
def evaluate(
    node: ASTNode,
    env: dict[str, float],
    fn_env: dict[str, UserFunction] | None = None,
) -> float:
    if fn_env is None:
        fn_env = {}
    ...
```

The `fn_env=None` default preserves backward compatibility: all existing call
sites that pass only `node` and `env` continue to work without modification.

Dispatch table:

| Node type   | Action |
|-------------|--------|
| `Number`    | Return `node.value` directly. |
| `UnaryOp`   | Return `-evaluate(node.operand, env, fn_env)`. |
| `BinaryOp`  | Evaluate both operands; apply operator; check `math.isinf` → `Overflow`. |
| `Name`      | Look up `node.name` in `env`; missing → `UndefinedVariable(node.name)`. |
| `Call`      | See § 3.1.1. |

#### 3.1.1 `Call` dispatch (extended in v0.4.0)

```
if node.func in _FUNCTION_TABLE:
    entry = _FUNCTION_TABLE[node.func]
    if len(node.args) != entry.arity:
        raise WrongArity(node.func, entry.arity)
    evaled = [evaluate(a, env, fn_env) for a in node.args]
    if entry.domain_check and not entry.domain_check(tuple(evaled)):
        raise DomainError()
    result = entry.fn(*evaled)
    if math.isinf(result):
        raise Overflow()
    return result
elif node.func in fn_env:                          # NEW v0.4.0
    return _call_user_fn(fn_env[node.func], node.args, env, fn_env)
else:
    raise UnknownFunction(node.func)
```

Built-ins are checked first. Because `execute_statement` rejects any `def`
statement that would shadow a built-in (`CannotRedefineBuiltin`), the `elif`
branch is never reachable for built-in names during normal execution — the
second check is a structural safety net only.

#### 3.1.2 `_call_user_fn(uf, arg_nodes, caller_env, caller_fn_env) → float`

Extracted as a named helper (not inlined) to keep the `Call` branch readable
and to provide a single test seam.

```python
def _call_user_fn(
    uf: UserFunction,
    arg_nodes: list[ASTNode],
    caller_env: dict[str, float],
    caller_fn_env: dict[str, UserFunction],
) -> float:
    if len(arg_nodes) != len(uf.params):
        raise WrongArity(uf.name, len(uf.params))
    evaled_args = [evaluate(a, caller_env, caller_fn_env) for a in arg_nodes]
    body_env: dict[str, float] = dict(_CONSTANTS_VALUES)
    body_env.update(zip(uf.params, evaled_args))
    return evaluate(uf.body, body_env, uf.available_fns)
```

Points of note:

- `body_env` is seeded from `_CONSTANTS_VALUES` only; the caller's `env` is
  intentionally excluded, enforcing the spec's "no outer variable capture" rule.
- `uf.available_fns` (the definition-time snapshot) is passed as `fn_env` for
  the recursive `evaluate` call, giving the body access only to functions that
  existed at definition time.
- Arguments are evaluated in `caller_env` / `caller_fn_env` before building
  `body_env`; this is correct because arguments are expressions in the caller's
  scope.

### 3.2 `execute_statement(stmt, env, fn_env) → float | None`

Signature:

```python
def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float | None:
```

Return value is `float | None`; `None` is returned for `FunctionDef` statements
(which have no numeric result). The CLI guards `format_result` accordingly.

Dispatch:

#### Assignment branch (unchanged)

```
result = evaluate(stmt.value, env, fn_env)
if stmt.name in _CONSTANTS:
    raise ConstantReassignment(stmt.name)
env[stmt.name] = result
return result
```

#### FunctionDef branch (new v0.4.0)

```
if stmt.name in _FUNCTION_TABLE:
    raise CannotRedefineBuiltin(stmt.name)
if stmt.name in fn_env:
    raise FunctionAlreadyDefined(stmt.name)
_validate_body_calls(stmt.body, fn_env)          # definition-time AST walk
fn_env[stmt.name] = UserFunction(
    name=stmt.name,
    params=stmt.params,
    body=stmt.body,
    available_fns=dict(fn_env),                  # snapshot AFTER validation
)
return None
```

Order of checks: built-in shadow check first, duplicate user-function check
second, body-AST validation third. The snapshot is taken after validation so
that if validation raises, `fn_env` is unmodified.

#### ASTNode (expression statement) branch (unchanged)

```
return evaluate(stmt, env, fn_env)
```

### 3.3 `_validate_body_calls(node, available_fns)` — definition-time forward-reference detection

```python
def _validate_body_calls(
    node: ASTNode,
    available_fns: dict[str, UserFunction],
) -> None:
    """Walk the body AST; raise UnknownFunction for any call not in available_fns
    or _FUNCTION_TABLE."""
    if isinstance(node, Call):
        if node.func not in _FUNCTION_TABLE and node.func not in available_fns:
            raise UnknownFunction(node.func)
        for arg in node.args:
            _validate_body_calls(arg, available_fns)
    elif isinstance(node, BinaryOp):
        _validate_body_calls(node.left, available_fns)
        _validate_body_calls(node.right, available_fns)
    elif isinstance(node, UnaryOp):
        _validate_body_calls(node.operand, available_fns)
    # Number and Name nodes contain no calls — no recursion needed.
```

Implementation: a simple recursive walk over the five `ASTNode` variants.
No `itertools` or visitor pattern is needed at this scale. The function is
module-private (`_validate_body_calls`). It raises on the first invalid call
found; no error accumulation.

Because `fn_env` does not yet contain the function being defined when this
walk runs, any self-call in the body raises `UnknownFunction(fn_name)`. Mutual
recursion is blocked by the same structural invariant.

### 3.4 `format_result(value: float) → str` (unchanged)

```python
def format_result(value: float) -> str:
    if value == int(value) and not math.isinf(value):
        return str(int(value))
    return str(value)
```

No changes in v0.4.0.

---

## 4. Public API / Interfaces

### Exports

The following names are part of the public interface consumed by `cli`
(`__main__.py`):

| Name | Type | Description |
|------|------|-------------|
| `UserFunction` | `dataclass(frozen=True)` | Runtime representation of a user-defined function |
| `evaluate` | `function` | Recursively evaluate an AST node to `float` |
| `execute_statement` | `function` | Execute one statement, updating `env`/`fn_env` in place |
| `format_result` | `function` | Convert `float` to display string |
| `_DEFAULT_ENV` | `MappingProxyType[str, float]` | Seed for the per-invocation variable env |

`_FUNCTION_TABLE`, `_CONSTANTS`, `_CONSTANTS_VALUES`, and `_call_user_fn` are
module-private. `FunctionEntry` is module-private.

### Signatures (complete)

```python
@dataclass(frozen=True)
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode
    available_fns: dict[str, "UserFunction"]

def evaluate(
    node: ASTNode,
    env: dict[str, float],
    fn_env: dict[str, UserFunction] | None = None,
) -> float: ...

def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float | None: ...

def format_result(value: float) -> str: ...
```

### CLI integration contract

The CLI initialises and threads both stores:

```python
env: dict[str, float] = dict(_DEFAULT_ENV)
fn_env: dict[str, UserFunction] = {}
last_result: float | None = None
for stmt in program.body:
    result = execute_statement(stmt, env, fn_env)
    if result is not None:
        last_result = result
if last_result is not None:
    print(format_result(last_result))
# If last_result is None (all stmts were def), print nothing; exit 0.
```

---

## 5. Error Handling

### 5.1 Error classes raised by the evaluator

| Condition | Class | Raised in | Description output |
|-----------|-------|-----------|--------------------|
| Call to an undefined function | `UnknownFunction(name)` | `evaluate` → `Call` branch; `_validate_body_calls` | `"undefined function: {name}"` |
| Wrong number of arguments | `WrongArity(name, expected)` | `evaluate` → `Call` branch (built-in and user fn); `_call_user_fn` | `"wrong number of arguments: {name} expects {expected} argument[s]"` |
| Argument outside mathematical domain | `DomainError()` | `evaluate` → `Call` branch (built-in only) | `"domain error"` |
| Division or modulo by zero | `DivisionByZero()` | `evaluate` → `BinaryOp` branch | `"division by zero"` |
| Result exceeds float range | `Overflow()` | `evaluate` → `BinaryOp` branch; built-in `Call` branch | `"overflow"` |
| Bare identifier not in env | `UndefinedVariable(name)` | `evaluate` → `Name` branch | `"undefined variable: {name}"` |
| Reassignment of constant | `ConstantReassignment(name)` | `execute_statement` → `Assignment` branch | `"cannot reassign constant: {name}"` |
| Duplicate user function definition | `FunctionAlreadyDefined(name)` | `execute_statement` → `FunctionDef` branch | `"function already defined: {name}"` |
| User function shadows a built-in | `CannotRedefineBuiltin(name)` | `execute_statement` → `FunctionDef` branch | `"cannot redefine built-in: {name}"` |

All classes are subclasses of `CalcError` defined in `errors.py`. None is
caught within the evaluator; all propagate to the CLI boundary.

### 5.2 Error message changes from v0.3.x (affects existing tests)

| Class | Old `description()` | New `description()` |
|-------|---------------------|---------------------|
| `UnknownFunction` | `"unknown function '{name}'"` | `"undefined function: {name}"` |
| `WrongArity` | `"'{name}' expects {n} argument[s]"` | `"wrong number of arguments: {name} expects {n} argument[s]"` |

Three test assertions in `test_errors.py` must be updated (lines 59, 63, 67).

### 5.3 Error ordering in `execute_statement` for `FunctionDef`

Checks are performed in this order, guaranteeing that the most informative
error is raised first:

1. `CannotRedefineBuiltin` — before modifying any state.
2. `FunctionAlreadyDefined` — before modifying any state.
3. `UnknownFunction` (via `_validate_body_calls`) — before writing to `fn_env`.
4. On success: insert into `fn_env`.

If any check fails, `fn_env` is left unmodified.

---

## 6. Test Strategy

Tests live in `tests/test_evaluator.py` under a clearly marked
`# v0.4.0 — user-defined functions` block (research #159). No new test file
is created.

### 6.1 Unit tests — `execute_statement` with hand-constructed AST nodes

These tests isolate the evaluator from the lexer and parser.

| Test name | What is verified |
|-----------|-----------------|
| `test_funcdef_stores_in_fn_env` | `execute_statement(FunctionDef("f", ["x"], body), env, fn_env)` returns `None` and inserts `UserFunction("f", ...)` into `fn_env`. |
| `test_funcdef_body_snapshot_excludes_later_fn` | Define `g` after `f`; confirm `f.available_fns` does not contain `g`. |
| `test_funcdef_cannot_redefine_builtin` | `execute_statement(FunctionDef("sqrt", ...), ...)` raises `CannotRedefineBuiltin("sqrt")`. |
| `test_funcdef_already_defined` | Second `execute_statement(FunctionDef("f", ...), ...)` raises `FunctionAlreadyDefined("f")`. |
| `test_funcdef_forward_reference_rejected` | Body AST references `g` before `g` is defined; raises `UnknownFunction("g")`. |
| `test_call_user_fn_single_param` | Hand-constructed `Call("f", [Number(3.0)])` with `fn_env` populated; returns correct float. |
| `test_call_user_fn_multi_param` | Two-parameter function called with two args; returns correct float. |
| `test_call_user_fn_wrong_arity` | Too few/too many args; raises `WrongArity`. |
| `test_call_user_fn_body_sees_constants` | Body references `pi`; result uses `math.pi`. |
| `test_call_user_fn_body_excludes_outer_var` | Outer `env` has `x=99`; body `Name("x")` with param `x=1` resolves to `1`, not `99`. |
| `test_call_user_fn_calls_sibling_fn` | Body calls another user function in `available_fns`; returns correct result. |

Use `@pytest.mark.parametrize` for arithmetic correctness cases where all
inputs share the form `call_user_fn_result(expr, arg) == expected_float`;
use individual named functions for error-path and structural tests.

### 6.2 Integration tests — full parse+evaluate path

One representative success case and one error case via the existing `eval_expr`
helper (which runs the full lex→parse→evaluate pipeline):

| Test name | Input | Expected |
|-----------|-------|----------|
| `test_eval_expr_user_fn_roundtrip` | `"def double(x) = x * 2; double(5)"` | `10.0` |
| `test_eval_expr_user_fn_unknown_at_call` | `"f(1)"` (no prior def) | raises `UnknownFunction("f")` |

### 6.3 Regression

All v0.1.x–v0.3.x evaluator tests must continue to pass. The only required
changes to existing tests are the three message-string updates in
`test_errors.py` described in § 5.2.

### 6.4 CLI-layer tests (`test_cli.py`)

The CLI test block exercises the evaluator end-to-end. Twelve individual
`test_` functions cover the v0.4.0 spec success criteria; four or more cover
failure modes. Names follow the `test_variable_assignment` convention, e.g.:

```
test_function_definition_no_output
test_function_call_single_arg
test_function_call_multi_param
test_function_body_uses_constant_pi
test_function_call_result_in_expression
test_function_composed_calls
test_function_definition_error_already_defined
test_function_definition_error_redefine_builtin
test_function_call_error_wrong_arity
test_function_call_error_undefined_function
```

---

## 7. Open Questions Resolved (from HLD § Open Questions item 3)

| Question | Resolution |
|----------|------------|
| Body-AST walk implementation | Recursive `_validate_body_calls` function; simple switch on node type; no visitor pattern needed. |
| `_call_user_fn` extracted vs inlined | Extracted as `_call_user_fn` private helper for readability and testability. |
| Behaviour when entire program is `def`-only | `last_result` remains `None`; CLI prints nothing and exits 0. This path is not explicitly tested in the v0.4.0 spec success criteria but the implementation handles it cleanly by construction. |

---

## 8. Dependencies

| Dependency | Used for |
|------------|----------|
| `parser.py` | `ASTNode`, `Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call`, `Assignment`, `FunctionDef`, `Statement` |
| `errors.py` | All `CalcError` subclasses listed in § 5.1 |
| `math` (stdlib) | `math.pi`, `math.e`, `math.isinf`, and built-in function implementations |
| `types` (stdlib) | `MappingProxyType` for `_DEFAULT_ENV` |
