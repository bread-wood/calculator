# Low-Level Design — Module: cli

**Module:** `cli`
**Milestone:** v0.2.0
**Date:** 2026-03-04
**File:** `src/calc/__main__.py`
**HLD ref:** `docs/design/v0.2.0/HLD.md § Module: cli`

---

## 1. Responsibilities

The `cli` module is the single entry point for the `calc` binary. It owns:

- Validating `sys.argv` (argument count and empty-string check)
- Orchestrating the pipeline: `Lexer` → `Parser` → `evaluate` → `format_result`
- Writing the result to `sys.stdout` on success
- Catching all `CalcError` exceptions, writing `error: <description>` to `sys.stderr`, and calling `sys.exit(1)`
- Printing the usage line when invoked with no arguments

No other module writes to stdout, stderr, or calls `sys.exit`.

### What this module does NOT do

- Parse or interpret expression tokens, AST nodes, or numeric values
- Define or validate function names, arities, or domain constraints
- Format floating-point results (delegated to `evaluator.format_result`)
- Define error message strings (delegated to `errors.error_message`)
- Read from stdin or support flags (no `--help`, `--verbose`, pipe mode)

---

## 2. Public API

### `main() -> None`

The sole public function. Registered as the `[project.scripts]` console entry point in
`pyproject.toml`:

```toml
[project.scripts]
calc = "calc.__main__:main"
```

Also invoked when the package is run with `python -m calc`.

**Signature:**
```python
def main() -> None: ...
```

**Behaviour:**

| Condition | Action | Exit |
|-----------|--------|------|
| `len(sys.argv) == 1` | print usage to stderr; `sys.exit(1)` | 1 |
| `len(sys.argv) > 2` | print `error_message(ExpectedSingleArg())`; `sys.exit(1)` | 1 |
| `sys.argv[1] == ""` | print `error_message(EmptyExpression())`; `sys.exit(1)` | 1 |
| Pipeline raises `CalcError` | print `error_message(e)` to stderr; `sys.exit(1)` | 1 |
| Success | print `format_result(result)` to stdout; return normally | 0 |

**Usage line** (printed to stderr, exit 1, when zero args):
```
usage: calc '<expression>'
```

This is a plain print, not an `error_message()` call — the spec requires this exact
literal without an `error:` prefix.

---

## 3. Data Structures

The `cli` module introduces no new data structures. It operates on:

| Value | Type | Source |
|-------|------|--------|
| `expression` | `str` | `sys.argv[1]` |
| `lexer` | `Lexer` | constructed inline |
| `ast` | `ASTNode` | `Parser(lexer).parse()` |
| `result` | `float` | `evaluate(ast)` |
| `output` | `str` | `format_result(result)` |
| `e` | `CalcError` subclass | raised by any pipeline stage |

---

## 4. Key Algorithms and Logic

### 4.1 `main()` Control Flow

```
def main():
    # Step 1 — Argument count check
    if len(sys.argv) == 1:
        print("usage: calc '<expression>'", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) != 2:
        print(error_message(ExpectedSingleArg()), file=sys.stderr)
        sys.exit(1)

    expression = sys.argv[1]

    # Step 2 — Empty-string check
    if expression == "":
        print(error_message(EmptyExpression()), file=sys.stderr)
        sys.exit(1)

    # Step 3 — Pipeline dispatch
    try:
        lexer  = Lexer(expression)
        ast    = Parser(lexer).parse()
        result = evaluate(ast)
    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)

    # Step 4 — Format and emit result
    print(format_result(result))
```

**Design notes:**
- Steps 1 and 2 occur before the `try` block because `ExpectedSingleArg` and
  `EmptyExpression` are CLI precondition failures, not pipeline failures. Raising them
  inside `try` would work but is less clear; keeping them outside makes the guard
  structure explicit.
- The single `try/except CalcError` block wraps the entire pipeline. There is no
  per-stage error handling inside `main`; all `CalcError` subclasses propagate uniformly
  to the catch site.
- `sys.exit(1)` is called immediately after writing to stderr; no further code runs.
- `evaluate(ast)` is called without an explicit `env` argument; it defaults to
  `_DEFAULT_ENV` (the `pi`/`e` constant table). `main()` does not pass or construct
  any environment dict.

### 4.2 v0.2.0 Changes vs. v0.1.0

The `cli` module is unchanged from v0.1.0. The pipeline (Steps 3–4) already calls
`evaluate(ast)` and `format_result(result)`. Because:

- The lexer, parser, and evaluator transparently handle function-call syntax and
  named constants
- All new errors (`DomainError`, `UnknownFunction`, `WrongArity`) are `CalcError`
  subclasses caught by the existing `except CalcError` handler
- `format_result` already produces correct integer/decimal output for function results

No changes to `__main__.py` are required for v0.2.0. The file is listed here for
completeness and test coverage purposes.

---

## 5. Error Handling

### 5.1 Error Ownership

`main()` is the **only** function that writes to stderr or calls `sys.exit`. All pipeline
layers raise `CalcError` subclasses and never write output directly.

### 5.2 Error Cases in v0.2.0

| Condition | `CalcError` subclass | stderr output |
|-----------|---------------------|---------------|
| Zero args | *(no exception — direct print)* | `usage: calc '<expression>'` |
| More than one arg | `ExpectedSingleArg` | `error: expected a single quoted expression` |
| Empty string arg | `EmptyExpression` | `error: empty expression` |
| Unknown character | `UnexpectedToken` | `error: unexpected token` |
| Valid token in invalid position | `UnexpectedToken` | `error: unexpected token` |
| Missing operand / premature EOF | `UnexpectedEnd` | `error: unexpected end of expression` |
| Division by zero | `DivisionByZero` | `error: division by zero` |
| Numeric overflow | `Overflow` | `error: overflow` |
| `sqrt(-1)`, `log(0)` | `DomainError` | `error: domain error` |
| `unknown(5)` | `UnknownFunction("unknown")` | `error: unknown function: unknown` |
| `sqrt()` | `WrongArity("sqrt", 1)` | `error: wrong number of arguments: sqrt expects 1` |
| `pow(2)` | `WrongArity("pow", 2)` | `error: wrong number of arguments: pow expects 2` |

All error strings are produced by `error_message(e)` from `errors.py`. `main()` never
hard-codes error strings (except the usage line, which is specified literally in the spec).

### 5.3 Exit Codes

| Outcome | Exit code |
|---------|-----------|
| Success | 0 |
| Any error | 1 |

No other exit codes are used in v0.2.0.

### 5.4 What `main()` Does NOT Catch

- `SystemExit` — not caught; raised by `sys.exit()` itself and propagates normally
- `KeyboardInterrupt` — not caught; Python handles this at the interpreter level
- `Exception` (non-`CalcError`) — not caught; any unexpected internal bug surfaces as
  a Python traceback, which is the correct behaviour for programming errors vs. user errors

---

## 6. Internal Structure

### 6.1 File Layout

The module is a single file: `src/calc/__main__.py`.

There are no private helpers. `main()` is the only function in the file.

### 6.2 `__main__` Guard

The file must end with:

```python
if __name__ == "__main__":
    main()
```

This makes both `python -m calc` and the `[project.scripts]` entry point work correctly,
and it prevents `main()` from running when the module is imported in tests.

### 6.3 Import Block

```python
import sys

from calc.errors    import CalcError, ExpectedSingleArg, EmptyExpression, error_message
from calc.lexer     import Lexer
from calc.parser    import Parser
from calc.evaluator import evaluate, format_result
```

No third-party or additional stdlib imports are needed. The `sys` import is the only
stdlib dependency.

---

## 7. Dependencies

### Module dependency graph

```
__main__.py
 ├── errors.py      (CalcError, ExpectedSingleArg, EmptyExpression, error_message)
 ├── lexer.py       (Lexer)
 ├── parser.py      (Parser)
 └── evaluator.py   (evaluate, format_result)
```

### What each dependency provides

| Dependency | Symbols used | Purpose |
|------------|-------------|---------|
| `errors` | `CalcError`, `ExpectedSingleArg`, `EmptyExpression`, `error_message` | Exception base class for `except` clause; two CLI-level error constructors; message formatter |
| `lexer` | `Lexer` | Tokenises the expression string |
| `parser` | `Parser` | Builds the AST from the token stream |
| `evaluator` | `evaluate`, `format_result` | Computes the float result; formats it as a string |

`cli` has no dependency on `functions.py` (if extracted) or any new v0.2.0 module. The
evaluator hides all function dispatch details.

---

## 8. Testing Strategy

### 8.1 Test File

`tests/test_cli.py`

### 8.2 Approach

All CLI tests use `subprocess.run` against `python -m calc`. This is the only layer that
can verify stdout/stderr separation and exit codes at the process boundary. No unit tests
for `main()` itself are needed — the function is a thin orchestrator with no extractable
pure logic.

```python
import subprocess, sys

def run_calc(*args):
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True,
        text=True,
    )
```

### 8.3 Assertion Pattern

```python
def test_sqrt_integer():
    r = run_calc("sqrt(9)")
    assert r.returncode == 0
    assert r.stdout.strip() == "3"
    assert r.stderr == ""

def test_domain_error():
    r = run_calc("sqrt(-1)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(DomainError())

def test_unknown_function():
    r = run_calc("unknown(5)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(UnknownFunction("unknown"))
```

Error message strings in assertions must be obtained from `error_message()` (not
hard-coded literals) to stay in sync with the canonical source in `errors.py`.
Floating-point comparisons use exact string equality — Python's `float.__repr__`
produces deterministic output on macOS and Linux for all spec-required values.

### 8.4 v0.2.0 Test Cases

All 21 spec acceptance criteria are covered by test functions in `test_cli.py`:

| Test name | Invocation | Expected stdout | Expected stderr | Exit |
|-----------|-----------|-----------------|-----------------|------|
| `test_sqrt_integer` | `sqrt(9)` | `3` | *(empty)* | 0 |
| `test_sqrt_irrational` | `sqrt(2)` | `1.4142135623730951` | *(empty)* | 0 |
| `test_abs` | `abs(-5)` | `5` | *(empty)* | 0 |
| `test_floor` | `floor(2.7)` | `2` | *(empty)* | 0 |
| `test_ceil` | `ceil(2.3)` | `3` | *(empty)* | 0 |
| `test_round` | `round(2.5)` | `3` | *(empty)* | 0 |
| `test_sin` | `sin(0)` | `0` | *(empty)* | 0 |
| `test_cos` | `cos(0)` | `1` | *(empty)* | 0 |
| `test_log` | `log(1)` | `0` | *(empty)* | 0 |
| `test_exp` | `exp(0)` | `1` | *(empty)* | 0 |
| `test_pow` | `pow(2, 10)` | `1024` | *(empty)* | 0 |
| `test_atan2` | `atan2(1, 1)` | `0.7853981633974483` | *(empty)* | 0 |
| `test_pi` | `pi` | `3.141592653589793` | *(empty)* | 0 |
| `test_e` | `e` | `2.718281828459045` | *(empty)* | 0 |
| `test_two_pi` | `2 * pi` | `6.283185307179586` | *(empty)* | 0 |
| `test_nested_calls` | `sqrt(pow(3, 2) + pow(4, 2))` | `5` | *(empty)* | 0 |
| `test_domain_error_sqrt` | `sqrt(-1)` | *(empty)* | `error: domain error` | 1 |
| `test_domain_error_log` | `log(0)` | *(empty)* | `error: domain error` | 1 |
| `test_unknown_function` | `unknown(5)` | *(empty)* | `error: unknown function: unknown` | 1 |
| `test_wrong_arity_sqrt` | `sqrt()` | *(empty)* | `error: wrong number of arguments: sqrt expects 1` | 1 |
| `test_wrong_arity_pow` | `pow(2)` | *(empty)* | `error: wrong number of arguments: pow expects 2` | 1 |

The v0.1.x cases (`test_addition`, `test_overflow`, `test_unexpected_token`, etc.) are
preserved unchanged as regression guards.

### 8.5 What Is Not Tested in `test_cli.py`

- Token-level correctness → `test_lexer.py`
- AST structure (Name, Call nodes) → `test_parser.py`
- Function dispatch, arity validation, domain checks → `test_evaluator.py`
- `format_result` edge cases → `test_evaluator.py`
- Error `description()` methods → `test_errors.py`

### 8.6 CI Matrix

Per HLD and research #42, #78: the `.github/workflows/ci.yml` matrix must include
`macos-latest` to satisfy the "passes clean on macOS and Linux" acceptance criterion.
This change belongs in the implementation PR, not this design document.

---

## 9. Performance

`main()` is a thin orchestrator. Its own CPU cost is negligible (two `len()` calls, one
string comparison, one `print`). All processing time is in the pipeline modules. The
100 ms spec budget is consumed by Lexer + Parser + Evaluator; `main()` contributes under
1 ms on any modern platform.

---

## 10. Non-Goals (v0.2.0)

- `--verbose` / `--help` flags
- Multiple expressions in a single invocation
- Reading from stdin (pipe mode)
- Structured (JSON) output
- Distinct exit codes per error class
- Interactive REPL mode

---

## 11. Open Questions Resolved

**HLD note: cli module unchanged in v0.2.0**
Confirmed. `__main__.py` requires zero modifications. All new v0.2.0 behaviour
(function dispatch, domain checks, new error types) is encapsulated in the evaluator
and errors modules. The `except CalcError` handler already catches all new subclasses
by inheritance.

**HLD Open Question 4: CI matrix syntax**
Resolved: extend `ci.yml` with `strategy.matrix.os: [ubuntu-latest, macos-latest]`.
This is a one-line addition to the existing workflow and is implemented in the
implementation PR, not a separate infrastructure PR (research #78).
