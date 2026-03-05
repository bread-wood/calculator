# Low-Level Design: `errors` module — Calculator v0.4.0

**Milestone:** v0.4.0
**Module:** `errors`
**File:** `src/calc/errors.py`
**Date:** 2026-03-05
**Status:** Draft
**Previous LLD:** `docs/design/v0.3.0/lld/errors.md`

---

## 1. Scope

This document is a **delta** from v0.3.0. Only changes are described here; refer to
`docs/design/v0.3.0/lld/errors.md` for data structures, algorithms, and interface
sections that are unchanged.

v0.4.0 makes four targeted changes to `errors.py`:

1. Modify `UnknownFunction.description()` — new wording required by spec.
2. Modify `WrongArity.description()` — new prefix and wording required by spec.
3. Add `FunctionAlreadyDefined(name: str)` — new error for duplicate `def` statements.
4. Add `CannotRedefineBuiltin(name: str)` — new error for `def` targeting a built-in name.

All other classes, the `CalcError` base, and `error_message()` are **unchanged**.

---

## 2. Responsibilities (delta)

Added responsibilities:
- Express `FunctionAlreadyDefined` and `CannotRedefineBuiltin` error conditions with
  human-readable `description()` messages matching the v0.4.0 spec.

Updated responsibilities:
- `UnknownFunction` and `WrongArity` description strings are updated to align with the
  rest of the error vocabulary (no quotes around function names; consistent prefixes).

What this module does NOT do — **unchanged** from v0.3.0.

---

## 3. Class Hierarchy (v0.4.0 state)

```
Exception
└── CalcError                       (base; description() -> str; abstract)
    ├── ExpectedSingleArg           (v0.1.0; unchanged)
    ├── EmptyExpression             (v0.1.0; unchanged)
    ├── UnexpectedToken             (v0.1.0; unchanged)
    ├── UnexpectedEnd               (v0.1.0; unchanged)
    ├── DivisionByZero              (v0.1.0; unchanged)
    ├── Overflow                    (v0.1.0; unchanged)
    ├── DomainError                 (v0.2.0; unchanged)
    ├── UnknownFunction             (v0.2.0; description() UPDATED)
    ├── WrongArity                  (v0.2.0; description() UPDATED)
    ├── UndefinedVariable           (v0.3.0; unchanged)
    ├── ConstantReassignment        (v0.3.0; unchanged)
    ├── FunctionAlreadyDefined      (new v0.4.0; name: str)
    └── CannotRedefineBuiltin       (new v0.4.0; name: str)
```

`FunctionAlreadyDefined` and `CannotRedefineBuiltin` are **sibling** direct subclasses
of `CalcError`. Neither is a subclass of the other. The semantics differ:
`FunctionAlreadyDefined` signals a duplicate user-function definition; `CannotRedefineBuiltin`
signals an attempt to shadow a built-in. Keeping them separate allows callers to
assert on exception type unambiguously in tests.

---

## 4. Public Interface (changed classes only)

### 4.1 `UnknownFunction` — updated `description()`

```python
class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined function: {self.name}"  # was: f"unknown function '{self.name}'"
```

**Change:** Prefix changes from `unknown function '...'` to `undefined function: ...`.
Quotes around the name are removed. The `name` attribute and `__init__` signature are
unchanged. All existing raise-sites in `evaluator.py` remain correct; no evaluator
changes are required.

**Rationale (research #155):** The new wording is consistent with `undefined variable: x`
and `cannot reassign constant: pi`. The old wording (`unknown function 'sqrt'`) quoted
the name inconsistently with other error classes. The v0.4.0 spec mandates the new form.

### 4.2 `WrongArity` — updated `description()`

```python
class WrongArity(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.name = name
        self.expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        noun = "argument" if self.expected == 1 else "arguments"
        return f"wrong number of arguments: {self.name} expects {self.expected} {noun}"
        # was: f"'{self.name}' expects {self.expected} {noun}"
```

**Change:** Prefix `wrong number of arguments: ` is prepended; quotes around `name`
are removed. The `name` and `expected` attributes and `__init__` signature are
unchanged. Pluralisation logic is retained.

**Rationale (research #155 Q4):** Option 4b (keep pluralisation, update prefix) is
chosen. `pow expects 2 arguments` is more informative than `pow expects 2`. The spec
mandates the new prefix; the added noun word does not conflict. Retaining pluralisation
is consistent with the existing behaviour and makes the message grammatically correct
for multi-argument functions.

### 4.3 `FunctionAlreadyDefined` — new

```python
class FunctionAlreadyDefined(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"function already defined: {self.name}"
```

**Pattern:** Identical to `UndefinedVariable` and `ConstantReassignment` — single
`name: str` arg, stored on `self`, passed to `super().__init__`, no quotes in message.

**Raised by:** `execute_statement()` in `evaluator.py` when a `FunctionDef` statement
names a function already present in `fn_env`. `errors.py` defines the class; `evaluator.py`
owns the guard logic.

### 4.4 `CannotRedefineBuiltin` — new

```python
class CannotRedefineBuiltin(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot redefine built-in: {self.name}"
```

**Pattern:** Same single-`name` pattern as `FunctionAlreadyDefined`. Note the hyphen
in `built-in` matches the spec's mandated output string.

**Raised by:** `execute_statement()` in `evaluator.py` when a `FunctionDef` statement
names a function already present in `_FUNCTION_TABLE`. Checked before the `fn_env`
duplicate check.

### 4.5 `error_message()` — unchanged

No change to implementation or signature. The function dispatches via Python method
resolution; new subclasses with correct `description()` overrides are handled
automatically without any modification to `error_message()`.

---

## 5. Data Structures (new classes only)

| Class | Attributes | Invariant |
|---|---|---|
| `FunctionAlreadyDefined` | `name: str` | non-empty string; the name as it appeared in the `def` statement |
| `CannotRedefineBuiltin` | `name: str` | must be a key in `_FUNCTION_TABLE` in `evaluator.py`; `errors.py` does not validate this |

No mutable state; all attributes set once in `__init__`.

For unchanged class data structures, see `docs/design/v0.3.0/lld/errors.md` §5.

---

## 6. Error Message Strings (v0.4.0 canonical)

| Class | `error_message(e)` output | Change from v0.3.0 |
|---|---|---|
| `ExpectedSingleArg` | `error: expected a single quoted expression` | — |
| `EmptyExpression` | `error: empty expression` | — |
| `UnexpectedToken` | `error: unexpected token` | — |
| `UnexpectedEnd` | `error: unexpected end of expression` | — |
| `DivisionByZero` | `error: division by zero` | — |
| `Overflow` | `error: overflow` | — |
| `DomainError` | `error: domain error` | — |
| `UnknownFunction("f")` | `error: undefined function: f` | **Updated** (was: `error: unknown function 'f'`) |
| `WrongArity("f", 1)` | `error: wrong number of arguments: f expects 1 argument` | **Updated** (was: `error: 'f' expects 1 argument`) |
| `WrongArity("f", 2)` | `error: wrong number of arguments: f expects 2 arguments` | **Updated** (was: `error: 'f' expects 2 arguments`) |
| `UndefinedVariable("x")` | `error: undefined variable: x` | — |
| `ConstantReassignment("pi")` | `error: cannot reassign constant: pi` | — |
| `FunctionAlreadyDefined("f")` | `error: function already defined: f` | **New** |
| `CannotRedefineBuiltin("sqrt")` | `error: cannot redefine built-in: sqrt` | **New** |

---

## 7. Key Algorithms and Logic (delta)

**Quoting conventions (updated):** v0.4.0 eliminates all quotes around function names
in error messages. The previous inconsistency (quotes in `UnknownFunction`/`WrongArity`,
no quotes in `UndefinedVariable`/`ConstantReassignment`) is resolved. v0.4.0 has a
uniform no-quotes style for all parameterised errors.

All other algorithm notes are unchanged from v0.3.0 — see §7 of the prior LLD.

---

## 8. Internal Structure (v0.4.0 state)

```
src/calc/errors.py
  CalcError                     (base)
  ExpectedSingleArg             (existing)
  EmptyExpression               (existing)
  UnexpectedToken               (existing)
  UnexpectedEnd                 (existing)
  DivisionByZero                (existing)
  Overflow                      (existing)
  DomainError                   (existing)
  UnknownFunction               (existing; description updated)
  WrongArity                    (existing; description updated)
  UndefinedVariable             (existing)
  ConstantReassignment          (existing)
  FunctionAlreadyDefined        (new)
  CannotRedefineBuiltin         (new)
  error_message()               (public function; unchanged)
```

Declaration order: base first, no-arg subclasses, single-arg subclasses, two-arg
subclasses, then `error_message`. The two new classes append naturally after
`ConstantReassignment`, maintaining the existing ordering discipline.

---

## 9. Error Handling Within This Module — unchanged

No change from v0.3.0. See §9 of the prior LLD.

---

## 10. Interaction with Other Modules (v0.4.0 state)

| Caller | Raises | Via |
|---|---|---|
| `__main__.py` | `ExpectedSingleArg`, `EmptyExpression` | arg-count / empty-string checks |
| `lexer.py` | `UnexpectedToken` | unrecognised character |
| `parser.py` | `UnexpectedToken`, `UnexpectedEnd` | syntax errors |
| `evaluator.py` | `DivisionByZero`, `Overflow`, `DomainError`, `UnknownFunction`, `WrongArity`, `UndefinedVariable`, `ConstantReassignment`, `FunctionAlreadyDefined`, `CannotRedefineBuiltin` | arithmetic, name, and function-definition errors |
| `__main__.py` | — | catches all `CalcError`; calls `error_message(e)` → stderr |

---

## 11. Migration from v0.3.0

### Files that change

| File | Change |
|---|---|
| `src/calc/errors.py` | Update `UnknownFunction.description()`; update `WrongArity.description()`; add `FunctionAlreadyDefined`; add `CannotRedefineBuiltin` |
| `tests/test_errors.py` | Update 3 existing assertions (lines 59, 63, 67); add 2 new test functions; extend import list |

### Files that do NOT change due to errors.py

- `src/calc/evaluator.py` — existing `UnknownFunction` and `WrongArity` raise-sites
  remain correct; updated `description()` methods propagate automatically. New raise-sites
  for `FunctionAlreadyDefined` and `CannotRedefineBuiltin` are added in `evaluator.py`
  but are driven by the evaluator LLD, not this one.
- `src/calc/__main__.py` — `except CalcError` handler catches all subclasses by
  inheritance; no change required.
- `tests/test_lexer.py`, `tests/test_parser.py`, `tests/test_cli.py` — do not import
  `UnknownFunction` or `WrongArity` directly; string assertions for these errors live
  in `test_cli.py` and will be updated as part of the CLI test additions (research #159).

---

## 12. Testing Strategy (delta)

**File:** `tests/test_errors.py`

### 12.1 Existing tests to update

Add a `# v0.4.0 — user-defined functions` comment block. Within it, update the three
existing message-string assertions that pin the old wording:

| Test (line) | Current assertion | Updated assertion |
|---|---|---|
| `test_unknown_function_message` (line 59) | `"error: unknown function 'sqrt'"` | `"error: undefined function: sqrt"` |
| `test_wrong_arity_singular` (line 63) | `"error: 'abs' expects 1 argument"` | `"error: wrong number of arguments: abs expects 1 argument"` |
| `test_wrong_arity_plural` (line 67) | `"error: 'pow' expects 2 arguments"` | `"error: wrong number of arguments: pow expects 2 arguments"` |

These three updates must land in the same PR as the `errors.py` changes to keep CI
green (research #159 §Q4).

### 12.2 New tests for v0.4.0

Add the following individual named test functions in the `# v0.4.0` block:

| Test | Assertion |
|---|---|
| `test_function_already_defined_message` | `error_message(FunctionAlreadyDefined("f")) == "error: function already defined: f"` |
| `test_function_already_defined_stores_name` | `FunctionAlreadyDefined("f").name == "f"` |
| `test_function_already_defined_inherits_calc_error` | `issubclass(FunctionAlreadyDefined, CalcError)` |
| `test_cannot_redefine_builtin_message` | `error_message(CannotRedefineBuiltin("sqrt")) == "error: cannot redefine built-in: sqrt"` |
| `test_cannot_redefine_builtin_stores_name` | `CannotRedefineBuiltin("sqrt").name == "sqrt"` |
| `test_cannot_redefine_builtin_inherits_calc_error` | `issubclass(CannotRedefineBuiltin, CalcError)` |
| `test_cannot_redefine_builtin_not_subclass_of_function_already_defined` | `not issubclass(CannotRedefineBuiltin, FunctionAlreadyDefined)` |

The last test guards the sibling-not-parent relationship that is semantically required.

### 12.3 Import list update

Add `FunctionAlreadyDefined` and `CannotRedefineBuiltin` to the import block at the
top of `test_errors.py`. Update `test_new_subclasses_inherit_from_calc_error` (or add
to `test_all_subclasses_inherit_from_calc_error`) to include both new classes.

### 12.4 Tricky edge cases

| Case | Test | Rationale |
|---|---|---|
| `UnknownFunction` no longer quotes name | Assert `"'sqrt'"` does NOT appear in `error_message(UnknownFunction("sqrt"))` | Regression guard for quote removal |
| `WrongArity` no longer quotes name | Assert `"'abs'"` does NOT appear in `error_message(WrongArity("abs", 1))` | Regression guard for quote removal |
| `CannotRedefineBuiltin` hyphen in `built-in` | Assert exact string `"error: cannot redefine built-in: sqrt"` | Hyphen is easy to accidentally omit |

### 12.5 What to mock

Nothing. `errors.py` has no I/O and no external dependencies; all tests are pure unit
tests.

### 12.6 Integration role

`tests/test_cli.py` v0.4.0 block will assert exact stderr output for:
- `def f(x) = x; def f(x) = x + 1` → `error: function already defined: f` (exit 1)
- `def sqrt(x) = x` → `error: cannot redefine built-in: sqrt` (exit 1)
- `f(1)` (with no prior def) → `error: undefined function: f` (exit 1)

These strings derive from the `description()` methods in this module; if wording
changes here, the CLI tests will catch the divergence.

---

## 13. Dependencies — unchanged

See `docs/design/v0.3.0/lld/errors.md` §13. No new imports; no change in what
imports `errors.py`.

---

## 14. Non-Goals — unchanged

See `docs/design/v0.3.0/lld/errors.md` §14.
