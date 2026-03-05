# Low-Level Design: `errors` module — Calculator v0.3.0

**Milestone:** v0.3.0
**Module:** `errors`
**File:** `src/calc/errors.py`
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Scope

This document covers the full design for `src/calc/errors.py` in v0.3.0 (Variables).
It resolves HLD open question #4 — the exact `description()` wording for the
renamed `UndefinedVariable` and the new `ConstantReassignment` class — and
specifies every change required to migrate from the v0.2.0 state.

---

## 2. Responsibilities

- Rename `UnknownName` → `UndefinedVariable` and update its `description()` to
  match the v0.3.0 spec wording.
- Add `ConstantReassignment(name: str)` for the new constant-protection error.
- Carry all existing v0.2.0 classes forward unchanged.
- Remain the single source of truth for all user-visible error strings.
- No external dependencies; stdlib only.

### What this module does NOT do

- Does not enforce constant protection (that is `evaluator.py`'s responsibility).
- Does not perform any I/O or logging.
- Does not assign exit codes (owned by `__main__.py`).
- Does not define `_CONSTANTS`; that lives in `evaluator.py`.

---

## 3. Class Hierarchy

```
Exception
└── CalcError                       (base; description() -> str; abstract)
    ├── ExpectedSingleArg           (v0.1.0; no args)
    ├── EmptyExpression             (v0.1.0; no args)
    ├── UnexpectedToken             (v0.1.0; no args)
    ├── UnexpectedEnd               (v0.1.0; no args)
    ├── DivisionByZero              (v0.1.0; no args)
    ├── Overflow                    (v0.1.0; no args)
    ├── DomainError                 (v0.2.0; no args)
    ├── UnknownFunction             (v0.2.0; name: str)
    ├── WrongArity                  (v0.2.0; name: str, expected: int)
    ├── UndefinedVariable           (renamed from UnknownName; name: str)
    └── ConstantReassignment        (new v0.3.0; name: str)
```

`UnknownName` is **removed**. Its only caller (`evaluator.py`) and its tests
are updated as part of this milestone. No other file references `UnknownName`.

---

## 4. Public Interface

### 4.1 `CalcError`

Unchanged from v0.2.0. `description()` raises `AttributeError` by default,
causing `error_message()` to re-raise as `TypeError` for any unregistered
subclass.

```python
class CalcError(Exception):
    def description(self) -> str:
        raise AttributeError  # abstract; subclasses must override
```

### 4.2 Existing v0.1.0 / v0.2.0 classes

All ten classes (`ExpectedSingleArg`, `EmptyExpression`, `UnexpectedToken`,
`UnexpectedEnd`, `DivisionByZero`, `Overflow`, `DomainError`,
`UnknownFunction`, `WrongArity`) are carried forward **unchanged**.

### 4.3 `UndefinedVariable` (renamed from `UnknownName`)

```python
class UndefinedVariable(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined variable: {self.name}"
```

**Key differences from `UnknownName`:**
- Class name changes: `UnknownName` → `UndefinedVariable`.
- Description changes: `"unknown name '{name}'"` → `"undefined variable: {name}"`.
  The new wording omits quotes around the name (per spec) and uses the word
  "variable" to match the v0.3.0 domain concept.
- The `name` attribute and `super().__init__(name)` call are identical to
  `UnknownName`.

**Rationale for rename (from research #111):** "undefined variable" precisely
matches the spec concept. Keeping the old name would require a mental translation
and accumulates conceptual debt as the codebase grows.

### 4.4 `ConstantReassignment` (new)

```python
class ConstantReassignment(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot reassign constant: {self.name}"
```

**Key design decisions:**
- No quotes around `name` in the format string (per spec: `"cannot reassign constant: pi"`, not `"cannot reassign constant: 'pi'"`). This is intentionally different from `UnknownFunction` which does quote its name.
- Raised exclusively by `execute_statement()` in `evaluator.py`, before any
  mutation of the environment dict. `errors.py` defines the class; `evaluator.py`
  owns the guard logic.
- `name` attribute follows the same convention as `UnknownFunction` and `UndefinedVariable`.

### 4.5 `error_message`

Unchanged from v0.2.0:

```python
def error_message(e: CalcError) -> str:
    try:
        return f"error: {e.description()}"
    except AttributeError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}") from None
```

---

## 5. Data Structures

All error classes are simple dataclasses in spirit (implemented as plain classes
for compatibility). Key invariants:

| Class | Attributes | Invariant |
|---|---|---|
| `UndefinedVariable` | `name: str` | non-empty string; the bare name as it appeared in source |
| `ConstantReassignment` | `name: str` | must be a member of `_CONSTANTS` in `evaluator.py`; `errors.py` does not validate this |

No mutable state; all attributes are set once in `__init__` and never modified.

---

## 6. Error Message Strings (canonical)

| Class | `error_message(e)` output |
|---|---|
| `ExpectedSingleArg` | `error: expected a single quoted expression` |
| `EmptyExpression` | `error: empty expression` |
| `UnexpectedToken` | `error: unexpected token` |
| `UnexpectedEnd` | `error: unexpected end of expression` |
| `DivisionByZero` | `error: division by zero` |
| `Overflow` | `error: overflow` |
| `DomainError` | `error: domain error` |
| `UnknownFunction("f")` | `error: unknown function 'f'` |
| `WrongArity("f", 1)` | `error: 'f' expects 1 argument` |
| `WrongArity("f", 2)` | `error: 'f' expects 2 arguments` |
| `UndefinedVariable("x")` | `error: undefined variable: x` |
| `ConstantReassignment("pi")` | `error: cannot reassign constant: pi` |

---

## 7. Key Algorithms and Logic

There are no non-trivial algorithms in this module. All logic is trivial
string formatting in `description()` methods and a single dict-free dispatch
in `error_message()`.

**`description()` dispatch:** `error_message()` calls `e.description()` via
normal Python method dispatch (virtual call). No type switching or `isinstance`
checks are needed. An unregistered subclass that omits `description()` inherits
`CalcError.description()`, which raises `AttributeError`, causing `error_message()`
to re-raise as `TypeError`. This is the existing guard, unchanged.

**Quoting conventions:**
- `UnknownFunction` — quotes around name: `unknown function 'sqrt'`
- `WrongArity` — quotes around name: `'abs' expects 1 argument`
- `UndefinedVariable` — **no quotes**: `undefined variable: x`
- `ConstantReassignment` — **no quotes**: `cannot reassign constant: pi`

The inconsistency (quotes vs. no quotes) is driven by the spec's mandated
output strings, not by a unified style rule.

---

## 8. Internal Structure

The module is a single flat file with no private helpers:

```
src/calc/errors.py
  CalcError                 (base)
  ExpectedSingleArg         (existing)
  EmptyExpression           (existing)
  UnexpectedToken           (existing)
  UnexpectedEnd             (existing)
  DivisionByZero            (existing)
  Overflow                  (existing)
  DomainError               (existing)
  UnknownFunction           (existing)
  WrongArity                (existing)
  UndefinedVariable         (renamed/updated)
  ConstantReassignment      (new)
  error_message()           (public function)
```

Declaration order: base first, no-arg subclasses, single-arg subclasses, two-arg
subclasses, then `error_message`. This matches v0.2.0 ordering extended naturally.

---

## 9. Error Handling Within This Module

- `error_message()` is the only function that can raise, and only raises `TypeError`
  on programmer error (unknown subclass). This is not a `CalcError`.
- No `CalcError` is raised by anything inside `errors.py`.
- No I/O, no imports from calc modules, no side effects.

---

## 10. Interaction with Other Modules

| Caller | Raises | Via |
|---|---|---|
| `__main__.py` | `ExpectedSingleArg`, `EmptyExpression` | arg-count / empty-string checks |
| `lexer.py` | `UnexpectedToken` | unrecognised character |
| `parser.py` | `UnexpectedToken`, `UnexpectedEnd` | syntax errors |
| `evaluator.py` | `DivisionByZero`, `Overflow`, `DomainError`, `UnknownFunction`, `WrongArity`, `UndefinedVariable`, `ConstantReassignment` | arithmetic and name/constant errors |
| `__main__.py` | — | catches all `CalcError`; calls `error_message(e)` → stderr |

---

## 11. Migration from v0.2.0

### Files that change

| File | Change |
|---|---|
| `src/calc/errors.py` | Remove `UnknownName`; add `UndefinedVariable` and `ConstantReassignment` |
| `src/calc/evaluator.py` | Update import (`UnknownName` → `UndefinedVariable`); update `raise UnknownName(...)` call; add `ConstantReassignment` import and guard |
| `tests/test_errors.py` | Update import line; update `test_unknown_name_message` assertion; update `test_unknown_name_stores_name`; update class list in `test_new_subclasses_inherit_from_calc_error` |

### Files that do NOT change

`tests/test_evaluator.py`, `tests/test_lexer.py`, `tests/test_parser.py`,
`tests/test_cli.py` — none of these import `UnknownName` directly. Only
`test_errors.py` requires mechanical updates.

---

## 12. Testing Strategy

**File:** `tests/test_errors.py`

### 12.1 Tests to update (mechanical renames)

| Old test | Required change |
|---|---|
| `test_unknown_name_message` | Import `UndefinedVariable`; assert `"error: undefined variable: pi_approx"` (no quotes) |
| `test_unknown_name_stores_name` | Import `UndefinedVariable`; replace `UnknownName("x")` with `UndefinedVariable("x")` |
| `test_new_subclasses_inherit_from_calc_error` | Replace `UnknownName` with `UndefinedVariable` in the class list |

### 12.2 New tests for v0.3.0

| Test | Assertion |
|---|---|
| `test_undefined_variable_message` | `error_message(UndefinedVariable("x")) == "error: undefined variable: x"` |
| `test_undefined_variable_stores_name` | `UndefinedVariable("x").name == "x"` |
| `test_constant_reassignment_message` | `error_message(ConstantReassignment("pi")) == "error: cannot reassign constant: pi"` |
| `test_constant_reassignment_stores_name` | `ConstantReassignment("pi").name == "pi"` |
| `test_constant_reassignment_no_quotes_in_message` | `ConstantReassignment("e")` → output contains `"e"` not `"'e'"` |
| `test_constant_reassignment_inherits_calc_error` | `issubclass(ConstantReassignment, CalcError)` |

**Why test no-quotes explicitly:** The quoting inconsistency between `UnknownFunction`
(quotes) and `ConstantReassignment` (no quotes) is intentional but easy to
accidentally introduce. An explicit assertion prevents regression.

### 12.3 Tricky edge cases

| Case | Test | Rationale |
|---|---|---|
| `UndefinedVariable` with a name that was previously `UnknownName` | Ensure old wording `"unknown name '...'"` does NOT appear | Regression guard for the rename |
| `ConstantReassignment` with `e` (single char) | `error_message(ConstantReassignment("e")) == "error: cannot reassign constant: e"` | Ensures format string handles short names correctly |
| `error_message(BogusError())` | `raises TypeError` | Existing guard must still hold with two new subclasses added |

### 12.4 What to mock

Nothing. `errors.py` has no I/O and no external dependencies; all tests are pure
unit tests with no mocking required.

### 12.5 Integration role

`tests/test_cli.py` integration tests will assert exact stderr output for:
- `calc "pi = 3"` → `error: cannot reassign constant: pi` (exit 1)
- `calc "x + 1"` → `error: undefined variable: x` (exit 1)

These strings are the canonical outputs from this module's `description()` methods,
so if `errors.py` strings change, the CLI tests will catch the divergence.

---

## 13. Dependencies

| Direction | Dependency |
|---|---|
| Imports from | none (stdlib only; not even `abc` or `dataclasses`) |
| Imported by | `evaluator.py`, `__main__.py`, `tests/test_errors.py`, `tests/test_cli.py` |

---

## 14. Non-Goals

- No `__str__` override.
- No logging hooks.
- No `(line, col, offset)` source-location payload (deferred to a future version).
- No chaining (`__cause__`) within `errors.py`; callers use `raise X from Y` as needed.
- No distinct exit codes per error type (owned by `__main__.py`).
