# Low-Level Design — Module: cli

**Module:** `cli`
**Milestone:** v0.1.0
**Date:** 2026-03-04
**File:** `src/calc/__main__.py`
**HLD ref:** `docs/design/v0.1.0/HLD.md § Module: cli`

---

## 1. Responsibilities

The `cli` module is the single entry point for the `calc` binary. It owns:

- Validating `sys.argv` (argument count and empty-string check)
- Orchestrating the pipeline: Lexer → Parser → Evaluator
- Formatting the numeric result as a string
- Writing the result to `sys.stdout` on success
- Catching all `CalcError` exceptions, writing `error: <message>` to `sys.stderr`, and calling `sys.exit(1)`
- Printing the usage line when invoked with no arguments

No other module writes to stdout, stderr, or calls `sys.exit`.

---

## 2. Data Structures

The `cli` module introduces no new data structures. It operates on:

| Value | Type | Source |
|---|---|---|
| `expression` | `str` | `sys.argv[1]` |
| `ast` | `ASTNode` (from `parser`) | `Parser(lexer).parse()` |
| `result` | `float` | `evaluate(ast)` |
| `output` | `str` | `format_result(result)` |
| `e` | `CalcError` subclass | raised by any pipeline stage |

---

## 3. Public API

### `main() -> None`

The sole public function. Registered as the `[project.scripts]` console entry point in
`pyproject.toml`:

```toml
[project.scripts]
calc = "calc.__main__:main"
```

Also called when the package is run with `python -m calc`.

**Signature:**
```python
def main() -> None: ...
```

**Behaviour:**

| Condition | Action | Exit |
|---|---|---|
| `len(sys.argv) == 1` | print usage to stderr; `sys.exit(1)` | 1 |
| `len(sys.argv) > 2` | raise / print `ExpectedSingleArg`; `sys.exit(1)` | 1 |
| `sys.argv[1] == ""` | raise / print `EmptyExpression`; `sys.exit(1)` | 1 |
| Pipeline raises `CalcError` | print `error_message(e)` to stderr; `sys.exit(1)` | 1 |
| Success | print `format_result(result)` to stdout; return normally | 0 |

**Usage line** (printed to stderr, exit 1, when zero args):
```
usage: calc '<expression>'
```

---

## 4. Algorithm — `main()` Control Flow

```
def main():
    # 1. Argument count check
    if len(sys.argv) == 1:
        print("usage: calc '<expression>'", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) != 2:
        print(error_message(ExpectedSingleArg()), file=sys.stderr)
        sys.exit(1)

    expression = sys.argv[1]

    # 2. Empty-string check
    if expression == "":
        print(error_message(EmptyExpression()), file=sys.stderr)
        sys.exit(1)

    # 3. Pipeline dispatch
    try:
        lexer  = Lexer(expression)
        ast    = Parser(lexer).parse()
        result = evaluate(ast)
    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)

    # 4. Format and emit result
    print(format_result(result))
```

**Notes:**
- The usage print (step 1, zero-args case) is a plain print, not a `CalcError` — the spec
  requires the literal string `usage: calc '<expression>'` with no `error:` prefix.
- `sys.exit(1)` is called **immediately** after writing to stderr; no further code runs.
- The `try/except` block wraps the entire pipeline. There is no per-stage error handling
  inside `main`; all `CalcError` subclasses propagate uniformly.

---

## 5. Error Handling

### 5.1 Error Ownership

`main()` is the **only** function that writes to stderr or calls `sys.exit`. All pipeline
layers (Lexer, Parser, Evaluator) raise `CalcError` subclasses; they never write output
directly.

### 5.2 Error Cases and Messages

| Condition | CalcError subclass | stderr output |
|---|---|---|
| Zero args | *(no exception — direct print)* | `usage: calc '<expression>'` |
| More than one arg | `ExpectedSingleArg` | `error: expected a single quoted expression` |
| Empty string arg | `EmptyExpression` | `error: empty expression` |
| Unknown character in input | `UnexpectedToken` | `error: unexpected token` |
| Valid token in invalid position | `UnexpectedToken` | `error: unexpected token` |
| Missing operand / premature EOF | `UnexpectedEnd` | `error: unexpected end of expression` |
| Division by zero | `DivisionByZero` | `error: division by zero` |
| Numeric overflow (isinf result) | `Overflow` | `error: overflow` |

All error strings are produced by `error_message(e)` from `errors.py`. `main()` never
hard-codes error strings.

### 5.3 Exit Codes

| Outcome | Exit code |
|---|---|
| Success | 0 |
| Any error | 1 |

No other exit codes are used in v0.1.0.

---

## 6. Imports and Dependencies

```python
import sys
from calc.errors   import CalcError, ExpectedSingleArg, EmptyExpression, error_message
from calc.lexer    import Lexer
from calc.parser   import Parser
from calc.evaluator import evaluate, format_result
```

Module dependency graph for `cli`:

```
__main__.py
 ├── errors.py      (CalcError, error_message)
 ├── lexer.py       (Lexer)
 ├── parser.py      (Parser)
 └── evaluator.py   (evaluate, format_result)
```

No third-party or stdlib imports beyond `sys`.

---

## 7. `__main__` Guard

The file must end with:

```python
if __name__ == "__main__":
    main()
```

This makes both `python -m calc` and the `[project.scripts]` entry point work correctly,
and it prevents `main()` from running when the module is imported in tests.

---

## 8. Test Strategy

### 8.1 Test File

`tests/test_cli.py`

### 8.2 Approach

All CLI tests use `subprocess.run` against `python -m calc`. This is the only layer that
can verify stdout/stderr separation and exit codes at the process boundary.

```python
import subprocess, sys

def run_calc(*args):
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True, text=True
    )
```

### 8.3 Test Cases

| Test name | Invocation | Expected stdout | Expected stderr | Exit code |
|---|---|---|---|---|
| `test_addition` | `calc '2 + 3'` | `5` | *(empty)* | 0 |
| `test_division_fractional` | `calc '10 / 4'` | `2.5` | *(empty)* | 0 |
| `test_precedence` | `calc '2 + 3 * 4'` | `14` | *(empty)* | 0 |
| `test_grouping` | `calc '(2 + 3) * 4'` | `20` | *(empty)* | 0 |
| `test_integer_output` | `calc '4 / 2'` | `2` | *(empty)* | 0 |
| `test_no_args` | `calc` | *(empty)* | contains `usage` | 1 |
| `test_too_many_args` | `calc '1' '2'` | *(empty)* | `error: expected a single quoted expression` | 1 |
| `test_empty_expression` | `calc ''` | *(empty)* | `error: empty expression` | 1 |
| `test_unexpected_token` | `calc 'abc'` | *(empty)* | `error: unexpected token` | 1 |
| `test_unexpected_end` | `calc '2 +'` | *(empty)* | `error: unexpected end of expression` | 1 |
| `test_division_by_zero` | `calc '1 / 0'` | *(empty)* | `error: division by zero` | 1 |
| `test_overflow` | `calc '1e308 * 1e308'` | *(empty)* | `error: overflow` | 1 |

### 8.4 Assertion Pattern

```python
def test_addition():
    r = run_calc("2 + 3")
    assert r.returncode == 0
    assert r.stdout.strip() == "5"
    assert r.stderr == ""

def test_no_args():
    r = run_calc()
    assert r.returncode == 1
    assert r.stdout == ""
    assert "usage" in r.stderr.lower()

def test_division_by_zero():
    r = run_calc("1 / 0")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == "error: division by zero"
```

Error message strings in assertions must be obtained from `error_message()` (not
hard-coded literals) to stay in sync with the canonical source of truth in `errors.py`.

### 8.5 What Is Not Tested Here

- Token-level correctness → `test_lexer.py`
- AST structure → `test_parser.py`
- Arithmetic precision → `test_evaluator.py`
- `format_result` edge cases → `test_evaluator.py`

---

## 9. Performance

`main()` is a thin orchestrator. Its own CPU cost is negligible (two `len()` calls, one
string comparison, one `print`). All processing time is in the pipeline modules. The
100 ms spec budget is consumed by Lexer + Parser + Evaluator; `main()` contributes under
1 ms on any modern platform.

---

## 10. Non-Goals (v0.1.0)

- `--verbose` / `--help` flags
- Multiple expressions in a single invocation
- Reading from stdin (pipe mode)
- Structured (JSON) output
- Distinct exit codes per error class

---

## 11. Open Questions Resolved

**HLD Open Question: stderr-write ownership**
Resolved: `main()` is the single owner of all stderr writes and `sys.exit` calls. No
pipeline layer writes to stderr directly.

**HLD Open Question: usage vs. error for zero-args case**
Resolved: zero args prints `usage: calc '<expression>'` (not `error: ...`) to stderr and
exits 1. Only the too-many-args case uses `error_message(ExpectedSingleArg())`.
