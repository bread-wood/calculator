# Research: Test Suite Organisation for v0.4.0 Function Features

**Issue:** #159
**Date:** 2026-03-05
**Milestone:** v0.4.0

---

## Summary

**Recommendation: Extend existing per-layer files; add individual `test_` functions
grouped by a comment block for v0.4.0 cases. Do not create a new `test_functions.py`.**
For the CLI layer, follow the existing pattern: individual named `test_` functions,
no `@pytest.mark.parametrize`. For the evaluator, test `execute_statement` directly
with hand-constructed AST nodes (existing pattern) for unit coverage, plus via the
full parse+evaluate path for integration confidence.

---

## Q1 — New file vs extend existing

### Option A — New `test_functions.py` (or `test_user_functions.py`)

- All function-related cases (lexer, parser, evaluator, errors, CLI) live in one file.
- Easy to find and review in isolation.
- **Cons:** Duplicates test infrastructure (`run_calc`, `eval_expr`, `execute_statement`
  imports) that already exists in the per-layer files. Breaks the established
  "one file per layer" discipline. Creates an awkward asymmetry: every other feature
  (assignments, constants, built-in functions) is covered inline in the per-layer
  files; user-defined functions would be the sole exception.

### Option B — Extend existing per-layer files (recommended)

Each of the five existing test files gains a clearly marked `# v0.4.0 — user-defined
functions` comment block with new test cases for that layer. The test infrastructure
(`run_calc`, imports) is already in place; no duplication.

**Why this is better:**
- Preserves the invariant that `test_lexer.py` covers the lexer, `test_parser.py`
  covers the parser, etc. — a reader inspecting one layer knows exactly where to look.
- The v0.3.0 precedent is clear: multi-statement and variable features were added
  directly to existing files (see `test_cli.py` lines 92–131), not split out.
- No infrastructure duplication.
- Five small additions are easier to review per-layer than one large cross-cutting file.

**Decision: Extend existing per-layer files.**

---

## Q2 — Individual `test_` functions vs `@pytest.mark.parametrize`

### Existing patterns

`test_evaluator.py` uses `@pytest.mark.parametrize` for arithmetic cases where all
inputs share identical structure (`eval_expr(s) == expected`). `test_cli.py` uses
individual named functions for every case, including the v0.3.0 block.

### Analysis

User-defined function tests vary significantly in what they assert:

- Some check stdout value (single-expression result after `def`)
- Some check stderr content and exit code
- Some are stateful sequences (define then call in same invocation)

`@pytest.mark.parametrize` works well when every test has identical structure. For
the CLI cases, the structure varies too much (some check stdout, some stderr, some
multi-step behaviour). Parametrising them would require a complex parameter schema
and would obscure intent — the failure message `FAILED test_cli.py::test_cli[case3]`
is less useful than `FAILED test_cli.py::test_function_call_single_arg`.

For `test_evaluator.py`, a small set of homogeneous cases (e.g. evaluation of a
`Call` node with different arguments after defining a function) could reasonably use
`@pytest.mark.parametrize`. Heterogeneous cases (define-and-call sequences,
arity-error paths) should be individual functions.

**Decision: Follow the `test_cli.py` pattern — individual named `test_` functions
throughout. Use `@pytest.mark.parametrize` only in `test_evaluator.py` for groups
of arithmetically homogeneous cases, matching the existing evaluator style.**

---

## Q3 — `execute_statement` vs full parse+evaluate path for evaluator unit tests

### Current pattern

`test_evaluator.py` tests `execute_statement` directly with hand-constructed AST
nodes (e.g. `test_execute_statement_assignment`, line 87). This provides precise
unit coverage of the evaluator independent of the lexer and parser.

### With user-defined functions

`FunctionDef` is the new statement type. `execute_statement(FunctionDef(...), env)`
stores the function in `env`. A subsequent `execute_statement(Call(...), env)`
retrieves and invokes it. Both paths should be tested at the unit level with
hand-constructed nodes so that evaluator bugs are diagnosable independently of
parser bugs.

The full parse+evaluate path (via `eval_expr`) should also be exercised for at
least one representative success case and one error case, to confirm integration,
but the primary coverage vehicle is the direct `execute_statement` path.

**Decision: Test `execute_statement` directly with hand-constructed `FunctionDef`
and `Call` AST nodes for unit coverage. Add one or two parse+evaluate integration
cases. This matches the existing dual-layer approach already present in
`test_evaluator.py`.**

---

## Q4 — Error message regression tests and issue #155

Issue #155 (resolved: see `docs/research/v0.4.0/155-error-class-design-for-function-errors.md`)
recommends modifying the existing `UnknownFunction` and `WrongArity` message strings
to align with v0.4.0 wording (`undefined function: f`, `wrong number of arguments:
f expects N`).

This means the following `test_errors.py` assertions **will fail** after the
`errors.py` change:

- `test_unknown_function_message` (line 59)
- `test_wrong_arity_singular` (line 63)
- `test_wrong_arity_plural` (line 67)

**Decision: Update those three test assertions as part of the same PR that modifies
the error classes, not as a separate task.** Splitting them into a separate cleanup
PR would leave CI in a broken state between the two PRs. The cost is low (three
one-line string changes). Track the dependency explicitly in the v0.4.0 implementation
issue for `errors.py`.

---

## Q5 — Coverage threshold in CI

`pyproject.toml` declares no `[tool.coverage]` section and no `--cov` flag. The CI
workflow (`.github/workflows/ci.yml`) runs `uv run pytest` with no coverage flags —
no `--cov`, no `--cov-fail-under`. There is **no enforced coverage threshold**.

New function code therefore cannot trigger a CI failure purely on coverage grounds.
However, the absence of a threshold is not a reason to leave new code uncovered:
uncovered code will fail silently in production. All new evaluator paths for
`FunctionDef` storage and user-function `Call` dispatch should be covered by the
`test_evaluator.py` unit tests described in Q3.

**Decision: No CI coverage action required. Aim for full coverage of new evaluator
and parser code by design, not enforcement.**

---

## Concrete recommendations for implementors

| Layer | File | Action |
|-------|------|--------|
| Lexer | `test_lexer.py` | Add `# v0.4.0` block: `DEF` token emission, `LPAREN`/`RPAREN`/`COMMA` if not yet tested |
| Parser | `test_parser.py` | Add `# v0.4.0` block: `FunctionDef` node shape, `Call` in expression position |
| Evaluator | `test_evaluator.py` | Add `# v0.4.0` block: `execute_statement(FunctionDef(...))` stores in env; `execute_statement(Call(...))` returns value; arity/unknown errors via direct AST; one `eval_expr` integration case |
| Errors | `test_errors.py` | Update 3 existing assertions per issue #155; add assertions for `FunctionAlreadyDefined` and `CannotRedefineBuiltin` |
| CLI | `test_cli.py` | Add `# v0.4.0` block: all 12 spec success criteria as individual named functions; 4+ failure-mode cases as individual named functions |

### Spec success criteria → test names (CLI layer)

Each of the 12 spec success-criteria lines maps 1:1 to a `test_` function with a
descriptive name, following the `test_variable_assignment` / `test_variable_reference`
naming convention already in `test_cli.py`. Examples:

```
test_function_definition_no_output
test_function_call_single_arg
test_function_call_multi_arg
test_function_body_uses_parameter
test_function_call_result_in_expression
test_recursive_function          # if in spec
test_nested_call                 # if in spec
```

Exact names should match the spec criterion text closely enough that the test name
is self-documenting.

---

## Follow-up issues implied

- Implementation issue for `test_lexer.py` additions (depends on #153 landing)
- Implementation issue for `test_parser.py` additions (depends on #156 landing)
- Implementation issue for `test_evaluator.py` additions (depends on #154, #157)
- Implementation issue for `test_errors.py` update (must land with #155 changes)
- Implementation issue for `test_cli.py` additions (end-to-end, depends on all above)
