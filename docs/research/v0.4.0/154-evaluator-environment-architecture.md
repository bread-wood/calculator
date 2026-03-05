# Research: Evaluator Environment Architecture for User-Defined Functions

**Issue:** #154
**Milestone:** v0.4.0
**Date:** 2026-03-05

---

## Decision Summary

**Recommendation: Option A — Split stores (`env` + `fn_env`).**

Keep `env: dict[str, float]` for variables; add a parallel
`fn_env: dict[str, UserFunction]` threaded through `evaluate` and
`execute_statement`. Variables and functions occupy separate namespaces by
design, which resolves the collision question explicitly.

---

## Question 1: Separate stores vs unified store

### Option A (Split) — **Chosen**

```python
@dataclass
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode
    fn_env_snapshot: dict[str, "UserFunction"]  # functions visible at definition time
```

`evaluate` and `execute_statement` each accept a second `fn_env` argument:

```python
def evaluate(
    node: ASTNode,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float: ...

def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float | None: ...
```

**Rationale:**

- **Type safety.** `env` remains `dict[str, float]`; no union narrowing is
  needed at every variable lookup. The evaluator's `Name` branch is unchanged.
- **Low disruption.** The only call-site change is threading a second argument.
  Existing tests pass `env` today; adding `fn_env={}` as a default keeps them
  green.
- **Scoping semantics fall out naturally.** The spec says function bodies may NOT
  reference outer variables. With split stores, `evaluate` called on a function
  body receives an `env` populated only with the function's own parameters (plus
  constants). No additional filtering step is required.
- **Snapshot semantics for `fn_env`.** At definition time, `UserFunction` stores
  a snapshot of the current `fn_env`. When a function body is evaluated, this
  snapshot is passed as `fn_env`, automatically enforcing the forward-reference
  prohibition: a function defined later cannot appear in an earlier snapshot.
- **Future REPL serialisability.** `UserFunction` is a pure dataclass (params +
  body AST + fn_env snapshot). All three fields are serialisable without redesign.
  The spec's constraint (§ Constraints: "function definitions must be representable
  as serializable values without redesigning the runtime") is satisfied.

### Option B (Union type) — Rejected

`dict[str, float | UserFunction]` conflates two distinct concepts and forces type
narrowing at every `env[name]` access. The scoping rule — function bodies do not
see outer variables — would require filtering the combined dict before passing it
to body evaluation, which is error-prone. Namespace collision becomes an implicit
possibility that callers must guard against.

### Option C (Environment class) — Deferred

An `Environment` dataclass wrapping both stores would be the right design if the
REPL required frequent mutation across many call sites. For v0.4.0 the overhead
outweighs the benefit; the split-store approach is straightforwardly refactorable
into an `Environment` class later if v0.5.x persistence demands it.

---

## Question 2: Namespace collision rule

**Decision: Variables and functions are separate namespaces. No collision is possible.**

With Option A, `env` holds floats and `fn_env` holds `UserFunction` objects.
The statement `x = 3; def x(n) = n` is valid: the variable `x` and the function
`x` coexist in separate dicts. Neither overwrites the other.

This matches the spec's two distinct error messages (`error: cannot reassign
constant: <name>` for variables, `error: function already defined: <name>` for
functions) and the fact that variables and functions have different lookup sites
(`Name` node vs `Call` node). A name collision between a variable and a function
is not addressable in the grammar — `x` (bare identifier) always resolves as a
variable; `x(...)` always resolves as a function call. There is no ambiguity.

**Duplicate function name** (`def f … ; def f …`) is still an error:
`execute_statement` checks `fn_env` before inserting and raises
`FunctionAlreadyDefined(name)` if the name is present.

---

## Question 3: Call-time function resolution and lookup order

**Order: built-ins first (enforced at definition time, not call time).**

When executing a `FunctionDef` statement, `execute_statement` checks
`_FUNCTION_TABLE` first:

```python
if stmt.name in _FUNCTION_TABLE:
    raise CannotRedefineBuiltin(stmt.name)
if stmt.name in fn_env:
    raise FunctionAlreadyDefined(stmt.name)
```

At call time (the `Call` branch of `evaluate`), the lookup checks `_FUNCTION_TABLE`
first, then `fn_env`. Because definition-time validation prevents any user-defined
function from shadowing a built-in, the call-time order is effectively irrelevant —
it is a safety net only.

```python
if node.func in _FUNCTION_TABLE:
    # built-in path (unchanged)
    ...
elif node.func in fn_env:
    # user-defined path (new)
    uf = fn_env[node.func]
    if len(node.args) != len(uf.params):
        raise WrongArity(node.func, len(uf.params))
    call_env = dict(_DEFAULT_ENV)  # constants only — no outer variables
    call_env.update(zip(uf.params, evaled_args))
    return evaluate(uf.body, call_env, uf.fn_env_snapshot)
else:
    raise UnknownFunction(node.func)
```

Note: the spec differentiates the error messages:
- existing built-in path → `error: unknown function: <name>` (current `UnknownFunction`)
- new user-defined path, undefined → `error: undefined function: <name>` (new error class)

The spec uses `unknown function` for built-in-style calls and `undefined function` for
user-defined calls (see success criteria line 7 and failure modes). Both are covered by
renaming/adding the appropriate `CalcError` subclass.

---

## Question 4: `execute_statement` return type for `def` statements

**Decision: return `None` for `def` statements; change return type to `float | None`.**

`execute_statement` currently returns `float` for all statements. A `FunctionDef`
statement has no numeric result. The return type becomes:

```python
def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float | None:
```

`__main__.py` already tracks `last_result` for the final print. The loop becomes:

```python
last_result: float | None = None
for stmt in program.body:
    result = execute_statement(stmt, env, fn_env)
    if result is not None:
        last_result = result
```

The final `format_result` call is guarded: if `last_result is None` (the entire
program consisted only of `def` statements), the output behaviour must be specified.
The spec's success criteria always end with an expression, so the case is not
tested; a reasonable choice is to print nothing (no stdout line) and exit 0.

---

## Updated Type Signatures

```python
# evaluator.py

@dataclass
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode
    fn_env_snapshot: dict[str, "UserFunction"]

def evaluate(
    node: ASTNode,
    env: dict[str, float],
    fn_env: dict[str, UserFunction] | None = None,
) -> float:
    if fn_env is None:
        fn_env = {}
    ...

def execute_statement(
    stmt: Statement,
    env: dict[str, float],
    fn_env: dict[str, UserFunction],
) -> float | None:
    ...
```

```python
# __main__.py

fn_env: dict[str, UserFunction] = {}
env: dict[str, float] = dict(_DEFAULT_ENV)
last_result: float | None = None
for stmt in program.body:
    result = execute_statement(stmt, env, fn_env)
    if result is not None:
        last_result = result
if last_result is not None:
    print(format_result(last_result))
```

---

## New Error Classes Required

```python
class FunctionAlreadyDefined(CalcError):
    def description(self) -> str:
        return f"function already defined: {self.name}"

class CannotRedefineBuiltin(CalcError):
    def description(self) -> str:
        return f"cannot redefine built-in: {self.name}"

class UndefinedFunction(CalcError):
    def description(self) -> str:
        return f"undefined function: {self.name}"

# WrongArity already exists — reuse for user-defined functions
# UnknownFunction retained for built-in lookup miss (should not occur after validation)
```

---

## Parser Changes Required (out of scope for this research)

The parser does not yet produce a `FunctionDef` AST node. A `FunctionDef`
dataclass and `def` keyword token will be needed. `Statement` will become
`Assignment | FunctionDef | ASTNode`. This is addressed in the parser research
issue (if any) or as part of implementation.

---

## Summary

| Question | Decision |
|----------|----------|
| Store structure | Option A: split `env: dict[str, float]` + `fn_env: dict[str, UserFunction]` |
| Namespace collision | Separate namespaces; variable `x` and function `x` can coexist |
| Lookup order | Built-ins win; enforced at definition time via `CannotRedefineBuiltin` |
| `execute_statement` return | `float \| None`; `None` for `def` statements |
