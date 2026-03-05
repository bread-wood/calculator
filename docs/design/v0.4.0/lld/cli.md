# Low-Level Design — `cli` Module (v0.4.0)

**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Draft
**Issue:** #193

---

## 1. Responsibility

The `cli` module (`src/calc/__main__.py`) is the entry point of the `calc` binary. Its
responsibilities are:

1. Validate CLI arguments and raise `ExpectedSingleArg` or `EmptyExpression` early.
2. Drive the lex → parse → execute pipeline by constructing a `Lexer`, calling
   `parse_program()`, and iterating `Program.body`.
3. Initialise `env: dict[str, float]` and `fn_env: dict[str, UserFunction]` before
   the statement loop and thread both through every `execute_statement()` call.
4. Track the result of the last expression statement; suppress stdout when all
   statements are `def` statements (last result is `None`).
5. Write the formatted result to stdout on success.
6. Catch any `CalcError`, write `error_message(e)` to stderr, and exit with code 1.

The CLI is the **sole owner** of stderr writes and process exit codes. No other module
writes to stderr or calls `sys.exit`.

---

## 2. Data Structures

### 2.1 `env: dict[str, float]`

A mutable dictionary mapping variable names (strings) to `float` values. Initialised
once per invocation from `dict(_DEFAULT_ENV)`, which seeds it with the built-in
constants `pi` and `e`. Each `Assignment` statement in the program updates this dict
in-place. The dict is created inside `main()` — not delegated to a factory — to keep
the full invocation lifecycle visible in one function.

### 2.2 `fn_env: dict[str, UserFunction]`

A mutable dictionary mapping user-defined function names (strings) to `UserFunction`
dataclass instances. Initialised as an empty `{}` inside `main()`. Each `FunctionDef`
statement adds one entry. The dict is passed by reference to every `execute_statement()`
call; each call may mutate it.

Both `env` and `fn_env` are created fresh per invocation. There is no module-level
mutable state in `__main__.py`.

### 2.3 `last_result: float | None`

A local variable in `main()`, initialised to `None`. Updated to the return value of
`execute_statement()` only when that value is not `None` (i.e. only for expression
statements and assignments, not for `def` statements). After the statement loop, if
`last_result is None` (the entire program consisted only of `def` statements), no
output is written to stdout.

---

## 3. Public API / Interfaces

### 3.1 `main() -> None`

The single public function exported by `__main__.py`. Called by the `[project.scripts]`
entry point (`calc = "calc.__main__:main"`) and by the `if __name__ == "__main__":` guard.

```python
def main() -> None:
    ...
```

Return type is `None`; all output channels are side effects (stdout, stderr, sys.exit).

### 3.2 `__main__.py` as a runnable module

`python -m calc` invokes `main()` via the standard `if __name__ == "__main__": main()`
guard. The `calc` binary invokes the same `main()` function through the entry-point
machinery. Both paths are identical.

### 3.3 Imports

```python
import sys
from calc.lexer import Lexer
from calc.parser import Parser
from calc.evaluator import (
    execute_statement,
    format_result,
    _DEFAULT_ENV,
    UserFunction,
)
from calc.errors import (
    CalcError,
    ExpectedSingleArg,
    EmptyExpression,
    error_message,
)
```

No imports from `calc.parser` node types are needed in `__main__.py`; the CLI treats
all statement types opaquely and dispatches via `execute_statement`.

---

## 4. Key Algorithms

### 4.1 Argument validation

```python
if len(sys.argv) != 2:
    raise ExpectedSingleArg()
source = sys.argv[1]
if not source.strip():
    raise EmptyExpression()
```

- `len(sys.argv) != 2` catches both too-few and too-many arguments (`sys.argv[0]` is
  the program name).
- The `strip()` check on `source` catches the empty-string and all-whitespace cases
  before handing off to the lexer.

### 4.2 Pipeline construction

```python
lexer = Lexer(source)
program = Parser(lexer).parse_program()
```

`Lexer` is constructed once and consumed by `Parser.parse_program()`. The resulting
`Program.body` is a list of `Statement` nodes (each a `Assignment | FunctionDef | ASTNode`).

### 4.3 Environment initialisation

```python
env: dict[str, float] = dict(_DEFAULT_ENV)
fn_env: dict[str, UserFunction] = {}
```

`dict(_DEFAULT_ENV)` creates a mutable copy of the `MappingProxyType` constant. The
original `_DEFAULT_ENV` is never mutated. `fn_env` starts empty; user-defined functions
accumulate into it during the statement loop.

### 4.4 Statement loop

```python
last_result: float | None = None
for stmt in program.body:
    result = execute_statement(stmt, env, fn_env)
    if result is not None:
        last_result = result
```

- `execute_statement` returns `float` for expression and assignment statements,
  `None` for `def` statements.
- Only non-`None` returns update `last_result`, so a trailing `def` statement does not
  suppress the result of an earlier expression.
- Both `env` and `fn_env` are passed by reference; mutations accumulate across
  iterations.

### 4.5 Output

```python
if last_result is not None:
    print(format_result(last_result))
```

- `format_result` produces `"5"` for whole-number floats and `str(value)` for decimals.
- If every statement in the program was a `def` (so `last_result` remains `None`),
  nothing is written to stdout and the process exits 0.

### 4.6 Error handling

```python
except CalcError as e:
    print(error_message(e), file=sys.stderr)
    sys.exit(1)
```

- A single `except CalcError` block at the top of `main()` catches any error raised
  anywhere in the pipeline (argument validation, lexing, parsing, evaluation).
- `error_message(e)` returns `"error: <e.description()>"`.
- `sys.exit(1)` is called only inside this except block; successful execution exits 0
  via normal function return.

### 4.7 Complete `main()` structure

```python
def main() -> None:
    try:
        if len(sys.argv) != 2:
            raise ExpectedSingleArg()
        source = sys.argv[1]
        if not source.strip():
            raise EmptyExpression()

        lexer = Lexer(source)
        program = Parser(lexer).parse_program()

        env: dict[str, float] = dict(_DEFAULT_ENV)
        fn_env: dict[str, UserFunction] = {}

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

---

## 5. Error Handling

The CLI is the top-level error boundary. Every `CalcError` subclass that can be raised
anywhere in the pipeline propagates unimpeded to the `except CalcError` handler in
`main()`. No error is caught and re-raised at an intermediate layer.

| Error class | Raise site | CLI visible condition |
|---|---|---|
| `ExpectedSingleArg` | `main()` | `len(sys.argv) != 2` |
| `EmptyExpression` | `main()` | `sys.argv[1].strip() == ""` |
| `UnexpectedToken` | `lexer.py`, `parser.py` | Malformed input |
| `UnexpectedEnd` | `parser.py` | Input ends mid-expression |
| `DivisionByZero` | `evaluator.py` | Division or modulo by zero at runtime |
| `Overflow` | `evaluator.py` | Float overflow at runtime |
| `DomainError` | `evaluator.py` | Argument outside built-in function's domain |
| `UnknownFunction` | `evaluator.py` | Call to undefined name; also at `def`-body walk time |
| `WrongArity` | `evaluator.py` | Argument count mismatch at call time |
| `UndefinedVariable` | `evaluator.py` | Bare name not in `env` |
| `ConstantReassignment` | `evaluator.py` | Assignment to `pi` or `e` |
| `FunctionAlreadyDefined` | `evaluator.py` | Duplicate `def` for same name |
| `CannotRedefineBuiltin` | `evaluator.py` | `def` targeting a built-in name |

All error paths produce exactly one line on stderr (`"error: <description>"`) and exit
code 1. Successful execution produces at most one line on stdout and exits 0.

---

## 6. File Layout

```
src/calc/__main__.py
```

Single file, no submodules. The file contains:

1. Module-level imports (stdlib first, then `calc.*`)
2. `main()` function
3. `if __name__ == "__main__": main()` guard

No module-level mutable state. No helper functions beyond `main()`.

---

## 7. Test Strategy

Tests live in `tests/test_cli.py`. A `# v0.4.0 — user-defined functions` block is
appended to the existing file after the v0.3.0 block.

### 7.1 Testing approach

`test_cli.py` uses a `run_calc(source)` helper that invokes the `calc` binary (or
`python -m calc`) as a subprocess and returns `(stdout, stderr, exit_code)`. All CLI
tests operate end-to-end through this helper, exercising the full pipeline from argument
to output. This is in contrast to `test_evaluator.py`, which tests the evaluator layer
in isolation.

Individual named `test_` functions are used throughout; `@pytest.mark.parametrize` is
not used for CLI tests. This matches the existing v0.3.0 test convention and produces
self-documenting failure messages.

### 7.2 Success criteria tests (12 functions)

Each of the 12 v0.4.0 spec success criteria maps to one named test function:

| Test function | Input | Expected stdout |
|---|---|---|
| `test_function_definition_no_output` | `"def f(x) = x"` | `""` (empty) |
| `test_function_call_single_arg` | `"def f(x) = x; f(3)"` | `"3"` |
| `test_function_call_multi_arg` | `"def add(a, b) = a + b; add(2, 3)"` | `"5"` |
| `test_function_body_uses_parameter` | `"def double(x) = x * 2; double(4)"` | `"8"` |
| `test_function_call_result_in_expression` | `"def f(x) = x + 1; f(2) + f(3)"` | `"7"` |
| `test_function_body_uses_builtin` | `"def s(x) = sqrt(x); s(9)"` | `"3"` |
| `test_function_body_uses_constant` | `"def r(x) = x * pi; r(1)"` | stdout contains `pi` value |
| `test_function_call_from_another_function` | `"def f(x) = x + 1; def g(x) = f(x) * 2; g(3)"` | `"8"` |
| `test_function_zero_params` | `"def one() = 1; one()"` | `"1"` |
| `test_function_shadows_variable_namespace` | `"x = 5; def x(a) = a; x(2)"` | `"2"` |
| `test_function_definition_exits_zero` | `"def f(x) = x"` | exit code 0 |
| `test_all_defs_no_stdout` | `"def f(x) = x; def g(x) = f(x)"` | `""` |

### 7.3 Failure mode tests (≥4 functions)

| Test function | Input | Expected stderr contains | Exit code |
|---|---|---|---|
| `test_function_already_defined_error` | `"def f(x) = x; def f(x) = x + 1"` | `"function already defined: f"` | 1 |
| `test_cannot_redefine_builtin_error` | `"def sqrt(x) = x"` | `"cannot redefine built-in: sqrt"` | 1 |
| `test_forward_reference_error` | `"def f(x) = g(x); def g(x) = x"` | `"undefined function: g"` | 1 |
| `test_wrong_arity_user_function` | `"def f(x) = x; f(1, 2)"` | `"wrong number of arguments"` | 1 |
| `test_unknown_function_error` | `"f(1)"` | `"undefined function: f"` | 1 |

### 7.4 Regression tests

All existing `test_cli.py` tests must continue to pass without modification, with the
sole exception of any test that asserts the old `UnknownFunction` or `WrongArity`
message strings. Those three assertions are updated as part of the `errors.py` changes
(tracked separately in the `errors` implementation issue; see research #159, §Q4).

No existing test is deleted. The v0.4.0 block is a pure addition.

### 7.5 What is not tested in `test_cli.py`

- Internal `env`/`fn_env` state after each statement — tested in `test_evaluator.py`
  via direct `execute_statement` calls.
- `FunctionDef` AST node shape — tested in `test_parser.py`.
- `DEF` token emission — tested in `test_lexer.py`.
- Error class `description()` strings — tested in `test_errors.py`.

---

## 8. Open Questions Resolved

From HLD §Open Questions item 5:

> **`cli` LLD** — Whether `fn_env` is constructed inside `main()` or delegated to a
> factory in `evaluator.py`; exact guard condition for suppressing stdout when
> `last_result is None`.

**Resolved:**

- `fn_env` is constructed as `{}` directly inside `main()`. Delegating to an
  `evaluator` factory would add indirection without benefit; the construction is a
  single expression with no logic to encapsulate. Both `env` and `fn_env` are
  initialised in the same two lines, making the invocation lifecycle self-contained
  and readable.

- The guard condition for suppressing stdout is `if last_result is not None`. The
  `last_result` variable is initialised to `None` and updated only when
  `execute_statement()` returns a non-`None` value. If every statement in the program
  is a `def` statement, `last_result` remains `None` and no output is written. Exit
  code is still 0. This is consistent with the v0.3.x behaviour where programs
  consisting entirely of assignment statements also produce no stdout output.
