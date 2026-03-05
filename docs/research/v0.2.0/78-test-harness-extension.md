# Research: Test Harness Extension for Function-Call Success and Error Cases

**Issue:** #78
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Branch:** 78-research-test-harness-extension-for-fun

---

## Summary

The v0.1.x test harness is **already fully capable** of covering all 22 v0.2.0 acceptance
criteria without any framework change. The only infrastructure gap is CI: the workflow runs
only on `ubuntu-latest` while the spec requires both macOS and Linux. All v0.2.0 cases —
including stderr/exit-1 error paths and floating-point outputs — follow patterns already
present in `test_cli.py`. Prior research (#42, #58) has mapped the full test distribution;
this document synthesises the findings and records the decisions needed before implementation.

---

## Q1 — What does the v0.1.x test harness look like?

**Mechanism:** pytest (not bats, shunit2, or any shell-based framework). The Makefile target
`make test` runs `uv run pytest tests/ -v`. There are no shell scripts driving the binary
directly.

**File layout:**

| File | Layer |
|---|---|
| `tests/test_lexer.py` | Unit — tokenizer |
| `tests/test_parser.py` | Unit — AST parser |
| `tests/test_evaluator.py` | Unit — evaluator + `format_result` |
| `tests/test_errors.py` | Unit — error classes and message strings |
| `tests/test_cli.py` | Integration — end-to-end via `subprocess.run` |

**How new cases are added:** Add a Python function (or parametrize entry) to the appropriate
test file. For v0.2.0, all 22 CLI acceptance criteria go into `test_cli.py` following the
existing `test_addition` / `test_division_by_zero` pattern. No new files or frameworks are
needed.

---

## Q2 — Does the harness separately capture stdout, stderr, and exit code?

**Yes — fully covered.** `test_cli.py` uses:

```python
def run_calc(*args):
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True,
        text=True,
    )
```

Every existing test asserts all three channels:

```python
assert r.stdout.strip() == "5"
assert r.stderr == ""
assert r.returncode == 0
```

Error-path tests (e.g. `test_division_by_zero`) already assert:

```python
assert r.stdout == ""
assert r.stderr.strip() == error_message(DivisionByZero())
assert r.returncode == 1
```

**Conclusion:** The five v0.2.0 error-path acceptance criteria (`sqrt(-1)`, `log(0)`,
`unknown(5)`, `sqrt()`, `pow(2)`) require zero harness changes. They are added as test
functions in `test_cli.py` using the exact same pattern. The error message strings for the
new error classes (`DomainError`, `UnknownFunction`, `WrongArgCount`) are tested separately
in `test_errors.py` — the same separation used for `DivisionByZero` in v0.1.x.

---

## Q3 — Is there a regression-guard for v0.1.x arithmetic cases?

**Yes.** The existing `test_cli.py` cases (`test_addition`, `test_precedence`,
`test_grouping`, `test_division_fractional`, `test_integer_output`, `test_division_by_zero`,
`test_overflow`, `test_unexpected_token`, etc.) are not removed or quarantined during v0.2.0
development. They run as part of `make test` on every commit.

The v0.1.x evaluator unit tests in `test_evaluator.py` are similarly preserved:

```python
@pytest.mark.parametrize("expr,expected", [
    ("2 + 3",       5.0),
    ("2 + 3 * 4",   14.0),   # operator precedence
    ("(2 + 3) * 4", 20.0),   # grouping
    ...
])
def test_evaluate(expr, expected):
    assert eval_expr(expr) == expected
```

Function-call parsing could silently break operator precedence if the parser changes
are not careful. The parametrized evaluator tests catch this immediately because they
exercise the full pipeline (lexer → parser → evaluator) and are run on every `make test`
invocation.

**No action required.** The regression guard is already in place.

---

## Q4 — How are the 12 new success-criteria outputs validated? Exact or approximate?

**Exact string comparison — confirmed correct.**

The harness always uses `r.stdout.strip() == "<expected>"`. There is no approximate
comparison. This is safe because:

1. The outputs are produced by Python's `math` module functions (`math.sqrt`,
   `math.atan2`, etc.), which are deterministic and return IEEE 754 double-precision
   values identical on all supported platforms (macOS, Linux).

2. The spec-specified values (`1.4142135623730951`, `0.7853981633974483`,
   `3.141592653589793`, `2.718281828459045`, `6.283185307179586`) are exactly the
   strings that Python's default `float.__repr__` produces for those values.

3. The existing `format_result` function (`test_evaluator.py:test_format_result`)
   already tests the integer-stripping rule (`5.0 → "5"`, `2.5 → "2.5"`) and is
   consistent with the spec's `sqrt(9) → "3"` requirement.

**Decision: use exact string comparison throughout.** No `pytest.approx`, no tolerance.
The two irrational outputs in the spec (`sqrt(2)` and `atan2(1,1)`) should be asserted
as:

```python
assert r.stdout.strip() == "1.4142135623730951"
assert r.stdout.strip() == "0.7853981633974483"
```

If a platform ever produces a different string for these values, that is a platform
issue, not a test design issue, and should fail loudly.

**Verification:** Prior research #57 confirmed that `format_result` outputs the exact
spec strings for all v0.2.0 success criteria. No changes to `format_result` are
required for floating-point outputs.

---

## Q5 — Are CI/CD jobs already in place? Do they run on macOS and Linux?

**CI exists but only runs Linux.** The workflow at `.github/workflows/ci.yml`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Run tests
        run: uv run pytest
      - name: Lint
        run: uv run ruff check
```

The v0.2.0 spec acceptance criterion #22 is: `make test passes clean on macOS and Linux`.
This criterion is **not currently verified by CI**.

**Required change** (one-line edit to `ci.yml`):

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
```

The Python stdlib `math` functions are portable; `uv` and `pytest` work identically on
both platforms. No test changes are needed — only the CI matrix change.

**Note on research commits:** Research PRs use `[skip ci]` in the commit message. The
matrix change should be made in the implementation PR (not this research commit) so that
CI actually validates both platforms from that point on.

---

## Decision Summary

| Question | Decision |
|---|---|
| Test framework | pytest + subprocess; no new framework |
| New test files | None — add to existing five test files |
| stderr + exit-code assertions | Already supported; zero harness changes |
| v0.1.x regression guard | Already in place; no action needed |
| Floating-point comparison | Exact string comparison throughout |
| CI cross-platform | Add `macos-latest` to matrix in implementation PR |

---

## Test Distribution (Delegated to #58)

Research #58 provides the complete per-file breakdown (~66 new test cases total). The
key additions for v0.2.0 are:

- **`test_errors.py`**: add `DomainError`, `UnknownFunction("foo")`,
  `WrongArgCount("sqrt", 1)` to the parametrize table.
- **`test_evaluator.py`**: parametrized dispatch tests for all 14 function/constant
  paths; `DomainError`, `UnknownFunction`, `WrongArgCount` raise tests with field assertions.
- **`test_cli.py`**: 21 test functions, one per spec acceptance criterion.
- **`test_lexer.py`** and **`test_parser.py`**: IDENT token and `Call`/`Name` AST node
  tests (see #58 for full enumeration).

---

## Answers to Acceptance Criteria

**Test harness mechanism:** pytest + subprocess in `tests/test_cli.py`. The `make test`
target runs `uv run pytest tests/ -v`. No shell scripts.

**stderr/exit-code assertions:** Fully covered by the existing harness. All error-path
tests in v0.1.x already assert `r.stderr.strip()` and `r.returncode == 1`. The five new
v0.2.0 error cases follow the same pattern with zero infrastructure changes.

**Floating-point comparison strategy:** Exact string comparison. The spec-required output
strings match Python's `float.__repr__` exactly on both macOS and Linux. No tolerance or
`pytest.approx` is used or needed.

**v0.1.x regression guard:** Active. Existing tests run unchanged under `make test`.
No quarantine or skip markers are introduced.

**CI cross-platform gap:** The only infrastructure change required for v0.2.0 is adding
`macos-latest` to the CI matrix. This belongs in the implementation PR, not a
separate infrastructure PR.
