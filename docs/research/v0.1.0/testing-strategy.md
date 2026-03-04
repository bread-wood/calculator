# Testing Strategy: Unit vs Integration vs End-to-End for CLI Expression Evaluator

**Issue:** #3
**Milestone:** v0.1.0
**Date:** 2026-03-04

---

## Recommendation

Use **pytest** with a three-layer test structure: unit tests for lexer and evaluator internals, and CLI integration tests via `subprocess`. No dependencies beyond pytest, which is already in the CI pipeline (`uv run pytest`).

---

## Language and Framework

The CI workflow (`ci.yml`) uses `uv run pytest` and `uv run ruff check`, confirming the implementation language is **Python**. pytest ships with the project toolchain via uv — no additional test runner is needed.

**Framework decision: pytest (stdlib-compatible, already required by CI)**

- `pytest` provides parameterized tests, readable assertions, and clean fixture management
- `subprocess.run` from the Python stdlib handles CLI integration tests
- Zero additional dependencies required

---

## Test Layer Decomposition

### Layer 1: Unit Tests — Lexer

Test the tokenizer in isolation. Each test passes a string and asserts the token list.

**Coverage targets:**

| Input | Expected tokens |
|-------|----------------|
| `"2 + 3"` | `[NUMBER(2), PLUS, NUMBER(3)]` |
| `"10 / 4"` | `[NUMBER(10), SLASH, NUMBER(4)]` |
| `"(2 + 3) * 4"` | `[LPAREN, NUMBER(2), PLUS, NUMBER(3), RPAREN, STAR, NUMBER(4)]` |
| `"2.5"` | `[NUMBER(2.5)]` |
| `"abc"` | raises `LexError("unexpected token")` |
| `""` | raises `LexError("empty expression")` |

**Why unit tests here:** Tokenization is pure input→output with no side effects. Fast, isolated tests catch edge cases (multi-digit numbers, decimals, unknown characters) without spinning up a process.

### Layer 2: Unit Tests — Parser and Evaluator

Test the parse+evaluate pipeline on token lists or expression strings. Focus on operator precedence, grouping, and arithmetic correctness.

**Coverage targets (maps directly to spec success criteria):**

| Expression | Expected result | Spec criterion |
|-----------|----------------|----------------|
| `"2 + 3"` | `5` | SC-1 |
| `"10 / 4"` | `2.5` | SC-2 |
| `"2 + 3 * 4"` | `14` | SC-3 (precedence) |
| `"(2 + 3) * 4"` | `20` | SC-4 (grouping) |
| `"4 / 2"` | `2` (not `2.0`) | SC-5 (integer output) |
| `"1 / 0"` | raises `EvalError("division by zero")` | SC-6 |
| `"2 +"` | raises `ParseError("unexpected end of expression")` | SC-8 |

**Overflow detection:** Produce an `EvalError("overflow")` when the result exceeds `float("inf")` or when integer arithmetic overflows the representable range. Test by evaluating a known-overflow expression.

**Integer vs decimal output formatting:** The formatter (the function that converts a numeric result to a string) should be tested independently:

```python
assert format_result(5.0) == "5"
assert format_result(2.5) == "2.5"
assert format_result(2.0) == "2"
```

This isolates the formatting logic from evaluation and prevents `2.0` regressions.

### Layer 3: CLI Integration Tests — subprocess

Exercise the compiled/runnable `calc` binary (or `python -m calc`) end-to-end. These tests are the authoritative check on exit codes, stdout/stderr separation, and exact error message strings.

**Pattern:**

```python
import subprocess, sys

def run_calc(*args):
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True, text=True
    )

def test_addition():
    r = run_calc("2 + 3")
    assert r.returncode == 0
    assert r.stdout.strip() == "5"
    assert r.stderr == ""

def test_division_by_zero():
    r = run_calc("1 / 0")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == "error: division by zero"

def test_no_arguments():
    r = run_calc()
    assert r.returncode == 1
    assert r.stdout == ""
    assert "usage" in r.stderr.lower()

def test_unexpected_token():
    r = run_calc("abc")
    assert r.returncode == 1
    assert r.stderr.strip() == "error: unexpected token"
```

**Why subprocess for the CLI layer:** The spec's stdout/stderr separation and exit code contracts can only be verified at the process boundary. Importing the module and calling functions does not catch a bug where error messages are accidentally written to stdout instead of stderr.

---

## Mapping: All 10 Spec Success Criteria → Test Layer

| # | Criterion | Layer |
|---|-----------|-------|
| 1 | `calc '2 + 3'` → `5`, exit 0 | CLI integration |
| 2 | `calc '10 / 4'` → `2.5`, exit 0 | CLI integration + evaluator unit |
| 3 | `calc '2 + 3 * 4'` → `14`, exit 0 | evaluator unit (precedence) |
| 4 | `calc '(2 + 3) * 4'` → `20`, exit 0 | evaluator unit (grouping) |
| 5 | `calc '4 / 2'` → `2` not `2.0` | formatter unit + CLI integration |
| 6 | `calc '1 / 0'` → stderr, exit 1 | CLI integration |
| 7 | `calc` no args → usage to stderr, exit 1 | CLI integration |
| 8 | `calc '2 +'` → `error: unexpected end of expression`, exit 1 | CLI integration |
| 9 | `calc 'abc'` → `error: unexpected token`, exit 1 | CLI integration + lexer unit |
| 10 | `make test` passes on macOS and Linux | all layers via `make test` |

---

## make test Target

```makefile
test:
	uv run pytest tests/ -v
```

No build step, no binary compilation. pytest discovers all `test_*.py` files under `tests/`. The `uv run` prefix ensures the correct virtualenv is used on both macOS and Linux, matching the CI environment exactly.

---

## Alternatives Considered

### Shell script for CLI tests
- Pro: No Python dependency for the CLI layer
- Con: Inconsistent behavior across macOS (`bash 3.x`) and Linux; harder to assert exact string matches; no parameterization; mixing shell and Python tests adds tooling complexity
- **Rejected**: Python subprocess is cleaner and already available

### End-to-end only (no unit tests)
- Faster to write initially, but gives no signal on which layer a failure originates in
- Precedence bugs and formatting bugs become hard to isolate
- **Rejected**: unit tests for evaluator and formatter are worth the minimal overhead

### pytest-subprocess or other mocking libraries
- Not needed: the CLI is a local process, not a network service; `subprocess.run` is sufficient
- **Rejected**: adds a dependency for no benefit

---

## Decision

| Concern | Approach |
|---------|----------|
| Test framework | pytest (already in CI via uv) |
| Lexer testing | pytest unit tests, assert token lists |
| Parser/evaluator testing | pytest unit tests, assert numeric results and exceptions |
| Output formatting | pytest unit tests on format_result() |
| CLI exit codes | subprocess integration tests |
| stdout/stderr separation | subprocess integration tests (capture_output=True) |
| Overflow | evaluator unit test + CLI integration test |
| make test | `uv run pytest tests/ -v` |
| External deps beyond toolchain | None |

The three-layer approach (lexer unit → evaluator unit → CLI integration) covers all 10 spec success criteria, runs identically on macOS and Linux via uv, and requires no dependencies beyond pytest.
