# Low-Level Design — `cli` module (v0.4.0)

**Module:** `cli` (`src/calc/__main__.py`)
**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Draft
**HLD ref:** `docs/design/v0.4.0/HLD.md` §Module: cli

---

## 1. Responsibilities

The `cli` module is the sole entry point of the `calc` binary. It owns:

1. Validating CLI arguments (exactly one positional argument required).
2. Driving the lex → parse → execute pipeline.
3. Initialising both the variable environment (`env`) and the function environment
   (`fn_env`) before the statement loop.
4. Threading `env` and `fn_env` through each statement in `Program.body`.
5. Tracking the last non-`None` result across statements.
6. Writing the final result to stdout (or nothing, if every statement was a `def`).
7. Catching all `CalcError` exceptions, writing `"error: <description>"` to stderr,
   and exiting with code 1.
8. Exiting with code 0 on success.

The module does **not** own: tokenisation, parsing, AST evaluation, error message
text, or user function storage — those belong to `lexer`, `parser`, `evaluator`, and
`errors` respectively.

---

## 2. File

```
src/calc/__main__.py
```

No other files are added or modified for this module.

---

## 3. Data structures

### 3.1 `env: dict[str, float]`

Mutable variable environment. Initialised from `dict(_DEFAULT_ENV)` (a shallow copy
of the `MappingProxyType` constant in `evaluator.py`) so that built-in named
constants (`pi`, `e`) are available on first use. Updated in-place by each
`Assignment` statement during the loop.

- **Key:** identifier name (str)
- **Value:** current numeric value (float)
- **Scope:** single invocation; discarded after `main()` returns
- **Mutation:** `execute_statement` writes to it; `main()` never reads it directly

### 3.2 `fn_env: dict[str, UserFunction]`

Mutable function environment. Initialised to `{}`. Populated in-place by each
`FunctionDef` statement.

- **Key:** function name (str)
- **Value:** `UserFunction` dataclass (defined in `evaluator.py`)
- **Scope:** single invocation; discarded after `main()` returns
- **Mutation:** `execute_statement` writes to it; `main()` never reads it directly

### 3.3 `last_result: float | None`

Local variable in `main()`. Tracks the result of the most recent statement that
returned a numeric value. Initialised to `None`. Updated only when
`execute_statement` returns a non-`None` value.

- `None` before any statement executes.
- `None` throughout a program consisting exclusively of `def` statements.
- Set to the `float` returned by the last `Assignment` or expression statement.

---

## 4. Key algorithm: `main()`

```
def main() -> None:
    1. if len(sys.argv) != 2:
           print(error_message(ExpectedSingleArg()), file=sys.stderr)
           sys.exit(1)

    2. source = sys.argv[1]

    3. try:
           lexer   = Lexer(source)
           parser  = Parser(lexer)
           program = parser.parse_program()

           env:     dict[str, float]       = dict(_DEFAULT_ENV)
           fn_env:  dict[str, UserFunction] = {}

           last_result: float | None = None

           for stmt in program.body:
               result = execute_statement(stmt, env, fn_env)
               if result is not None:
                   last_result = result

           if last_result is not None:
               print(format_result(last_result))

       except CalcError as e:
           print(error_message(e), file=sys.stderr)
           sys.exit(1)
```

**Notes:**

- `ExpectedSingleArg` validation happens **before** the `try` block so the argument
  count check itself is not obscured by the generic `CalcError` handler. (The
  `ExpectedSingleArg` path also calls `sys.exit(1)` directly; it is not raised as an
  exception in this path.)
- The single `except CalcError` block catches every downstream error including new
  v0.4.0 errors (`FunctionAlreadyDefined`, `CannotRedefineBuiltin`) — no changes
  needed to the error-handling block for new error types.
- `format_result` is called only once, on the final result, just before printing.
- If `last_result is None` (all statements were `def` statements), no output is
  written to stdout and the process exits 0.

### 4.1 Resolution of HLD open question #5

> Whether `fn_env` is constructed inside `main()` or delegated to a factory in
> `evaluator.py`.

**Decision: constructed inside `main()`.**

`fn_env` is an ordinary `dict` literal `{}`. There is no logic to encapsulate; a
factory function would add indirection without benefit. `env` follows the same
pattern (`dict(_DEFAULT_ENV)`). Symmetry and simplicity favour local construction.

> Exact guard condition for suppressing stdout when `last_result is None`.

**Decision: `if last_result is not None:`**

This is the minimal, direct expression of the condition. An all-`def` program
legitimately has no numeric output; the guard must cover both the "no statements"
edge case and the "all statements were defs" case with the same expression.

---

## 5. Public API / interfaces

### 5.1 Imports consumed

| Symbol | Source module |
|--------|--------------|
| `sys` | stdlib |
| `Lexer` | `calc.lexer` |
| `Parser` | `calc.parser` |
| `execute_statement` | `calc.evaluator` |
| `format_result` | `calc.evaluator` |
| `_DEFAULT_ENV` | `calc.evaluator` |
| `UserFunction` | `calc.evaluator` |
| `CalcError` | `calc.errors` |
| `ExpectedSingleArg` | `calc.errors` |
| `error_message` | `calc.errors` |

`UserFunction` is imported for the type annotation of `fn_env` only; it is not
instantiated in `main()`.

### 5.2 Exported interface

The module exports a single callable:

```python
def main() -> None: ...
```

`__main__.py` also contains:

```python
if __name__ == "__main__":
    main()
```

No other names are exported. The module is not intended for use as a library.

---

## 6. Error handling

### 6.1 Argument count error

Checked before entering the pipeline. Uses `len(sys.argv) != 2`.

```
$ calc
error: expected a single expression argument
```

```
$ calc '1+2' extra
error: expected a single expression argument
```

Exit code: 1. Output on stderr.

### 6.2 All other errors

All `CalcError` subclasses are caught by a single `except CalcError as e:` block.
The handler:

1. Calls `error_message(e)` → `"error: " + e.description()`
2. Writes the string to `sys.stderr`
3. Calls `sys.exit(1)`

This includes all v0.4.0 errors without any modification to the handler:

| Error | Trigger |
|-------|---------|
| `FunctionAlreadyDefined(name)` | Second `def` for the same name |
| `CannotRedefineBuiltin(name)` | `def` targeting a built-in function name |
| `UnknownFunction(name)` | Call to undefined function (at definition time or eval time) |
| `WrongArity(name, expected)` | Call with wrong argument count |

### 6.3 Stdout / stderr contract

- Success output → stdout only, no trailing label
- Error output → stderr only, prefixed `"error: "`
- Exit 0 on success (including all-`def` programs)
- Exit 1 on any `CalcError`

---

## 7. Control flow diagram

```
main()
  │
  ├─ len(sys.argv) != 2 ──► stderr + exit(1)
  │
  ├─ Lexer(source)
  ├─ Parser(lexer).parse_program() → Program
  │      │
  │      └─ CalcError ──► stderr + exit(1)
  │
  ├─ env  = dict(_DEFAULT_ENV)
  ├─ fn_env = {}
  ├─ last_result = None
  │
  └─ for stmt in program.body:
         │
         ├─ execute_statement(stmt, env, fn_env) → float | None
         │      │
         │      └─ CalcError ──► stderr + exit(1)
         │
         └─ if result is not None: last_result = result
                │
  ┌────────────┘
  │
  ├─ last_result is not None ──► print(format_result(last_result)) → stdout
  └─ last_result is None     ──► (no output)

exit(0)
```

---

## 8. Test strategy

Tests live in `tests/test_cli.py`. A new `# v0.4.0 — user-defined functions` block
is appended. No new test file is created (research #159).

All test functions use the existing `run_calc(args)` helper, which captures stdout,
stderr, and the exit code.

### 8.1 Success cases (12 named functions)

Each function maps 1:1 to a v0.4.0 spec success criterion.

| Test function name | What it asserts |
|--------------------|-----------------|
| `test_function_definition_no_output` | `def f(x) = x; 0` → only `"0"` on stdout (def produces no output) |
| `test_function_definition_only_no_output` | `def f(x) = x` → empty stdout, exit 0 |
| `test_function_call_single_arg` | `def double(x) = x*2; double(3)` → `"6"` |
| `test_function_call_multi_arg` | `def add(a,b) = a+b; add(3,4)` → `"7"` |
| `test_function_body_uses_parameter` | `def sq(x) = x*x; sq(5)` → `"25"` |
| `test_function_call_result_in_expression` | `def inc(x) = x+1; inc(2)*3` → `"9"` |
| `test_function_uses_builtin_constant` | `def circ(r) = 2*pi*r; circ(1)` → `format_result(2*math.pi)` |
| `test_function_uses_builtin_function` | `def f(x) = sqrt(x); f(4)` → `"2"` |
| `test_function_calls_earlier_function` | `def sq(x)=x*x; def cube(x)=sq(x)*x; cube(3)` → `"27"` |
| `test_function_zero_params` | `def one() = 1; one()` → `"1"` |
| `test_function_shadows_no_variable` | `x=5; def f(x)=x*2; f(3)` → `"6"` (body param, not outer var) |
| `test_function_and_variable_same_name` | `f=9; def f(x)=x+1; f(2)` → `"3"` (separate namespaces) |

### 8.2 Error / failure cases (≥ 4 named functions)

| Test function name | Expected stderr fragment | Exit code |
|--------------------|--------------------------|-----------|
| `test_function_already_defined_error` | `"error: function already defined: f"` | 1 |
| `test_cannot_redefine_builtin_error` | `"error: cannot redefine built-in function: sqrt"` | 1 |
| `test_function_wrong_arity_error` | `"error: wrong number of arguments: f expects 2 argument(s)"` (or singular) | 1 |
| `test_function_unknown_function_error` | `"error: undefined function: g"` | 1 |
| `test_forward_reference_error` | `def f(x) = g(x); def g(x) = x` → `"error: undefined function: g"` | 1 |

### 8.3 Regression

All pre-existing `test_cli.py` test functions must continue to pass. No changes to
existing test functions are required except the three message-string updates in
`test_errors.py` (owned by the `errors` module LLD, not this one).

### 8.4 Test naming convention

Follow the existing `test_variable_assignment` / `test_variable_reference` style:
`test_<concept>_<qualifier>`, lowercase, underscores. Each function is self-contained
with no shared state between tests.

---

## 9. Constraints and invariants

- `fn_env` is never passed to `evaluate()` directly by `main()`; it is passed to
  `execute_statement()`, which is responsible for forwarding it.
- `main()` never inspects the contents of `fn_env` or `env` after the loop.
- `main()` never instantiates `UserFunction` directly.
- `format_result` is called at most once per invocation (on `last_result`).
- The module must not import `UserFunction` for any purpose other than the type
  annotation; zero coupling to the `UserFunction` internals.
- No module-level mutable state is introduced; all state lives in local variables
  inside `main()`.

---

## 10. Dependencies

```
cli (__main__.py)
  ├── calc.lexer       (Lexer)
  ├── calc.parser      (Parser)
  ├── calc.evaluator   (execute_statement, format_result, _DEFAULT_ENV, UserFunction)
  └── calc.errors      (CalcError, ExpectedSingleArg, error_message)
```

No new dependencies are introduced in v0.4.0. The only change relative to v0.3.0 is:

1. `fn_env: dict[str, UserFunction] = {}` is initialised alongside `env`.
2. `execute_statement(stmt, env, fn_env)` is called with the additional `fn_env`
   argument (the v0.3.0 signature was `execute_statement(stmt, env)`).
3. `UserFunction` is imported for the type annotation.
