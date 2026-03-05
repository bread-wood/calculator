# Research: Test Infrastructure for Exit-Code and Stderr Acceptance Criteria

**Issue:** #42
**Date:** 2026-03-04
**Branch:** 42-research-test-infrastructure-for-exit-c

---

## Findings

### 1. Existing Test Mechanism

The v0.1.x test suite uses **pytest** (not bats, shunit2, or any shell-based framework). Tests are pure Python, located in `tests/`. The Makefile target `make test` runs `uv run pytest tests/ -v`.

The suite is structured in four layers:
- `test_lexer.py` — unit tests for the tokenizer
- `test_parser.py` — unit tests for the AST parser
- `test_evaluator.py` — unit tests for the evaluator and `format_result`
- `test_errors.py` — unit tests for the error-message module
- `test_cli.py` — end-to-end integration tests via `subprocess.run`

### 2. Stderr and Exit-Code Support — Already Present

`test_cli.py` uses `subprocess.run(..., capture_output=True, text=True)` and asserts all three channels on every test:

```python
assert r.stdout.strip() == "5"
assert r.stderr == ""
assert r.returncode == 0
```

Error-path tests (e.g. `test_division_by_zero`, `test_unexpected_token`) already assert:
- `r.stdout == ""`
- `r.stderr.strip() == error_message(SomeError())`
- `r.returncode == 1`

**The v0.1.x harness fully supports stderr and exit-code assertions.** No new framework (bats, shunit2, etc.) is needed. All five v0.2.0 error-path acceptance criteria (`sqrt(-1)`, `log(0)`, `unknown(5)`, `sqrt()`, `pow(2)`) can be covered by adding tests to `test_cli.py` following the existing pattern.

### 3. Unit vs. End-to-End Coverage

The project maintains both:
- **Unit tests** for lexer, parser, evaluator, and errors modules.
- **End-to-end CLI tests** in `test_cli.py`.

For v0.2.0, the new components are:
- A **function registry** (table of name → arity + callable)
- A **domain-error** exception class (analogous to `DivisionByZero`)

Recommendation: **Add unit tests for both**, following the existing pattern:

| Component | Where to test |
|---|---|
| `DomainError`, `UnknownFunction`, `WrongArgCount` exception classes + `error_message` entries | `test_errors.py` |
| Function registry dispatch, arity check, domain-error raise | `test_evaluator.py` |
| End-to-end CLI: all 22 acceptance criteria | `test_cli.py` |

Unit coverage of the registry (`sqrt`, `abs`, `pow`, etc.) is cheap and isolates failures. End-to-end coverage is still required because the spec acceptance criteria are defined at the CLI boundary. Both layers are valuable and consistent with the v0.1.x architecture.

### 4. Output Format Rule — Already Covered

`test_cli.py:test_integer_output` tests `4 / 2 → "2"`, and `test_evaluator.py:test_format_result` parametrizes the `format_result` function directly including `(5.0, "5")`, `(2.0, "2")`, `(2.5, "2.5")`.

For v0.2.0, the spec requires `sqrt(9) → 3` (not `3.0`). This is covered by the existing `format_result` logic (`5.0 → "5"`), but an explicit end-to-end test `calc 'sqrt(9)'` → `"3"` should be added to `test_cli.py` to match the acceptance criterion exactly.

### 5. CI — macOS Coverage Gap

The existing `.github/workflows/ci.yml` runs only on `ubuntu-latest`. The v0.2.0 spec requires `make test` to pass on **both macOS and Linux**.

Current workflow:
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
```

The Python stdlib functions used (`math.sqrt`, `math.log`, etc.) are portable, and the test runner (pytest via uv) works identically on both platforms. However, the spec acceptance criterion `make test passes clean on macOS and Linux` is currently not automatically verified.

**Recommendation:** Extend the CI matrix to include `macos-latest`:

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
```

This is a one-line change and satisfies the cross-platform requirement without any new tooling.

---

## Answers to Research Questions

| # | Question | Answer |
|---|---|---|
| 1 | Test mechanism | pytest + subprocess; no shell-based framework |
| 2 | stderr + exit-code support | Yes — fully supported in existing harness; no changes needed |
| 3 | Unit vs. end-to-end separation | Both exist; add unit tests for new error types and registry, plus end-to-end for all 22 criteria |
| 4 | CI cross-platform | CI runs Linux only; add `macos-latest` to the matrix |
| 5 | Output format rule for function results | `format_result` unit tests cover it; add explicit `sqrt(9) → "3"` CLI test |

---

## Acceptance Criteria Responses

**Test runner and stderr/exit-code:** The existing pytest + subprocess harness handles all three channels. No new framework required.

**Minimal addition for error-path tests:** Zero infrastructure changes. Add ~10 parametrized test cases to `test_cli.py` and `test_errors.py` following the existing pattern.

**Unit tests for function registry:** Yes — add to `test_evaluator.py`. Unit tests give faster, more precise feedback than end-to-end for registry dispatch and arity validation.

**CI for macOS + Linux:** Extend `.github/workflows/ci.yml` with a 2-entry `os` matrix. This is the only infrastructure change required for v0.2.0.

---

## Summary

The v0.1.x test infrastructure is **already fit for purpose** for v0.2.0's error-path acceptance criteria. The only gap is CI: adding `macos-latest` to the matrix satisfies the cross-platform requirement. No new test frameworks, no shell scripts, no bats. All 22 acceptance criteria are testable today using the existing pytest + subprocess pattern.
