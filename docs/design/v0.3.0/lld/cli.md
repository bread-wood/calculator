# Low-Level Design — Module: cli (v0.3.0)

**Milestone:** v0.3.0
**Module:** cli
**File:** `src/calc/__main__.py`
**Date:** 2026-03-05
**Status:** Draft

---

## Overview

The `cli` module is the entry point for the `calc` command. It owns argument
validation, pipeline orchestration (lex → parse → execute), environment
construction, result formatting, and process exit codes. All user-visible I/O
passes through this module; no other module writes to stdout or stderr.

**What this module does NOT do:**
- Tokenise, parse, or evaluate expressions (delegated to `lexer`, `parser`, `evaluator`).
- Define error types (delegated to `errors`).
- Persist state between invocations.
- Handle interactive REPL sessions.
- Support Windows-specific argument encoding.

---

## Public Interface

### `main() -> None`

Entry point, called from `if __name__ == "__main__": main()` at the bottom of
`__main__.py` and registered as the `calc` console-script in `pyproject.toml`.

**Behaviour:**
1. Validate `sys.argv` length; write usage or `error_message(ExpectedSingleArg())`
   to stderr and exit 1 on failure.
2. Reject an empty-string argument with `error_message(EmptyExpression())`.
3. Build a fresh mutable `env` dict by copying `_DEFAULT_ENV` from `evaluator`.
4. Lex and parse the source string into a `Program`.
5. Iterate `Program.body`, calling `execute_statement(stmt, env)` for each statement.
6. Print the result of the **last** statement with `format_result(value)`.
7. Catch any `CalcError`, write `error_message(e)` to stderr, exit 1.

**Signature:**
```python
def main() -> None: ...
```

No return value; process exit codes are the only observable output beyond
stdout/stderr.

---

## Data Structures

The `cli` module introduces no new types. Key types consumed from dependencies:

| Type | Source | Role |
|---|---|---|
| `Program` | `parser` | AST root; `.body: list[Statement]` iterated by main loop |
| `Statement` | `parser` | `Assignment \| ASTNode` union; dispatched by `execute_statement` |
| `dict[str, float]` | built-in | Mutable variable environment; constructed in `main()`, threaded through `execute_statement` calls |
| `CalcError` | `errors` | Base class caught at the top level |

### Environment construction

```python
env: dict[str, float] = dict(_DEFAULT_ENV)   # fresh copy; never mutates the module-level proxy
```

`_DEFAULT_ENV` is a `MappingProxyType` in `evaluator.py` (v0.3.0 spec decision,
research #114). Copying it into a plain mutable dict gives `main()` a user-variable
frame that includes the built-in constants as starting values. `_CONSTANTS` in the
evaluator prevents reassignment of those names regardless of their presence in `env`.

---

## Key Algorithms and Logic

### Main execution loop

```
argv[1]
  │
  ▼
[ argument validation ]
  │ ok
  ▼
env = dict(_DEFAULT_ENV)          ← fresh per invocation
  │
  ▼
Lexer(source) → Parser → Program
  │
  ▼  iterate Program.body
  ├─ execute_statement(stmt, env)  → result: float
  ├─ execute_statement(stmt, env)  → result: float
  └─ execute_statement(stmt, env)  → last_result: float
  │
  ▼
print(format_result(last_result))
```

### Last-statement result

`execute_statement` returns `float` for both `Assignment` statements and
expression statements (see evaluator LLD). The loop retains the return value of
the final call as `last_result` and always prints it, even when the last
statement is an assignment (`x = 5` prints `5`). This matches the spec
requirement: *"prints the value of the last statement"*.

```python
last_result: float = 0.0       # satisfies type checker; overwritten on first iteration
for stmt in program.body:
    last_result = execute_statement(stmt, env)
print(format_result(last_result))
```

`Program.body` is non-empty by the time `main()` reaches the loop — the empty
expression check at argument-validation time (step 2) and the parser's own
`UnexpectedEnd` guard ensure at least one statement is always present.

### Trailing-semicolon programs

A source string like `"x = 5;"` produces a `Program` with one statement because
`parse_program()` accepts a trailing `;` without adding an empty statement
(research #110, Q3). The loop runs once and prints `5`. No special handling is
needed in `main()`.

### Edge case: last statement is an assignment

```
calc 'x = 42'       → stdout: 42
calc 'x = 3; y = 4' → stdout: 4
```

`execute_statement` returns the assigned value for `Assignment` nodes (evaluator
LLD decision). `main()` does not need to distinguish statement types; it always
prints `last_result`.

---

## Internal Structure

`__main__.py` contains exactly one public function (`main`) and one module-level
guard:

```python
# src/calc/__main__.py

import sys

from calc.errors import CalcError, ExpectedSingleArg, EmptyExpression, error_message
from calc.lexer import Lexer
from calc.parser import Parser
from calc.evaluator import evaluate, execute_statement, format_result, _DEFAULT_ENV

def main() -> None:
    ...

if __name__ == "__main__":
    main()
```

No private helpers are needed; all logic fits in `main()` without exceeding
~30 lines. If the function grows (e.g. for a future `--verbose` flag), extract
`_build_env()` or `_run_pipeline()` at that point — not preemptively.

---

## Error Handling

### Errors raised by this module directly

| Condition | Error written to stderr | Exit code |
|---|---|---|
| `len(sys.argv) == 1` | `usage: calc '<expression>'` (plain string, not via `error_message`) | 1 |
| `len(sys.argv) > 2` | `error_message(ExpectedSingleArg())` | 1 |
| `sys.argv[1] == ""` | `error_message(EmptyExpression())` | 1 |

The no-arg case uses a hand-written usage line (not `error_message`) to match
the v0.2.x contract. Changing it would break the existing `test_no_args` test.

### Errors propagated from the pipeline

All `CalcError` subclasses raised inside the `try` block are caught uniformly:

```python
try:
    lexer = Lexer(expression)
    program = Parser(lexer).parse_program()
    env: dict[str, float] = dict(_DEFAULT_ENV)
    last_result: float = 0.0
    for stmt in program.body:
        last_result = execute_statement(stmt, env)
except CalcError as e:
    print(error_message(e), file=sys.stderr)
    sys.exit(1)
```

| Source | Error type | Example trigger |
|---|---|---|
| `Lexer` | `UnexpectedToken` | `calc '@'` |
| `Parser` | `UnexpectedEnd`, `UnexpectedToken` | `calc '2 +'` |
| `Evaluator` (`evaluate`) | `DivisionByZero`, `Overflow`, `DomainError`, `UnknownFunction`, `WrongArity`, `UndefinedVariable` | `calc '1/0'`, `calc 'x + 1'` |
| `Evaluator` (`execute_statement`) | `ConstantReassignment` | `calc 'pi = 3'` |

No error type is caught and swallowed; all propagate to the top-level handler
and produce `"error: <description>"` on stderr with exit code 1.

`TypeError` from the evaluator (malformed AST node type) is **not** a `CalcError`
and is deliberately not caught — it surfaces as an unhandled exception, which is
correct because it signals a programming error in the parser/evaluator, not a
user input error.

---

## Testing Strategy

### Unit tests (none needed for `main()` itself)

`main()` is pure orchestration with no isolatable sub-logic beyond what is
already covered by unit tests in `test_lexer.py`, `test_parser.py`,
`test_evaluator.py`, and `test_errors.py`. Writing unit tests that mock the
pipeline inside `main()` would produce fragile tests without coverage value.

### Integration tests (`tests/test_cli.py`)

All tests use `subprocess.run([sys.executable, "-m", "calc", ...])` to exercise
the real binary path. This verifies the console-script entry point and process
exit codes, which cannot be tested any other way.

**Existing tests to preserve unchanged:**

All v0.2.x tests in `test_cli.py` must pass without modification.

**New v0.3.0 test cases required:**

| Test name | Input | Expected stdout | Expected stderr | Exit code |
|---|---|---|---|---|
| `test_variable_assignment` | `'x = 5'` | `5` | — | 0 |
| `test_variable_reference` | `'x = 5; x + 1'` | `6` | — | 0 |
| `test_multi_statement` | `'x = 5; y = x * 2; y + 1'` | `11` | — | 0 |
| `test_last_stmt_is_assignment` | `'x = 3; y = 4'` | `4` | — | 0 |
| `test_trailing_semicolon` | `'x = 5;'` | `5` | — | 0 |
| `test_constant_pi_readable` | `'pi * 2'` | `6.283185307179586` | — | 0 |
| `test_constant_e_readable` | `'e'` | `2.718281828459045` | — | 0 |
| `test_constant_reassignment_pi` | `'pi = 3'` | — | `error: cannot reassign constant: pi` | 1 |
| `test_constant_reassignment_e` | `'e = 1'` | — | `error: cannot reassign constant: e` | 1 |
| `test_undefined_variable` | `'x + 1'` | — | `error: undefined variable: x` | 1 |
| `test_error_in_second_statement` | `'x = 1; x / 0'` | — | `error: division by zero` | 1 |
| `test_integer_result_from_variable` | `'x = 4; x / 2'` | `2` | — | 0 |

**What to mock:** nothing. Integration tests run the real subprocess; there is
nothing worth mocking in the CLI module.

---

## Dependencies

| Module | Import | Used for |
|---|---|---|
| `calc.errors` | `CalcError`, `ExpectedSingleArg`, `EmptyExpression`, `error_message` | Argument validation errors; top-level error formatting |
| `calc.lexer` | `Lexer` | Tokenisation |
| `calc.parser` | `Parser` | Parsing; returns `Program` |
| `calc.evaluator` | `execute_statement`, `format_result`, `_DEFAULT_ENV` | Statement execution; result formatting; env initialisation |
| `sys` (stdlib) | `sys.argv`, `sys.stderr`, `sys.exit` | Argument access, error output, exit codes |

No third-party libraries are used or needed.

### Note on `_DEFAULT_ENV` import

`_DEFAULT_ENV` is a private module-level name in `evaluator.py`. Importing it in
`__main__.py` is intentional: `main()` owns environment construction and must copy
the canonical default values to initialise a fresh `env` dict per invocation. If
`evaluator` exposes a `make_env() -> dict[str, float]` factory in a future version,
`main()` should switch to that; for v0.3.0 the direct import is the simplest correct
approach.
