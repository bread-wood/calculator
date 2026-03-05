# Low-Level Design: `errors` module — Calculator v0.2.0

**Milestone:** v0.2.0
**Module:** `errors`
**File:** `src/calc/errors.py`
**Date:** 2026-03-04
**Status:** Draft

---

## 1. Scope

This document covers the full design for `src/calc/errors.py` in v0.2.0. It
resolves HLD open question #2 (`UnknownName` vs `UnknownFunction`), specifies the
migration from `_MESSAGES` dict to `description()` methods, and defines every
class, method, and test case for this module.

---

## 2. Responsibilities

- Define `CalcError` as the single base class for all user-visible errors.
- Add `description() -> str` as an abstract method on `CalcError`, replacing the
  `_MESSAGES` dict approach.
- Carry all six existing subclasses forward with minimal change (only adding
  `description()` bodies).
- Add three new v0.2.0 subclasses: `UnknownFunction`, `WrongArity`, `DomainError`.
- Resolve open question #2: introduce a separate `UnknownName` class for bare
  `Name` node lookup misses.
- Keep `error_message(e)` as the single public formatter; simplify it to call
  `e.description()` directly, preserving the `TypeError` guard via `isinstance`.
- No external dependencies; stdlib only.

---

## 3. Open Question Resolution: `UnknownName` vs `UnknownFunction`

**Decision:** Add a distinct `UnknownName(name: str)` subclass.

**Rationale:**

| Concern | Detail |
|---------|--------|
| User-facing message clarity | `"unknown function 'sqrt'"` is correct for `sqrt(2)`. For a bare `pi_approx` typo, `"unknown name 'pi_approx'"` is more accurate and helpful. |
| Future variable support | When user variables are added (`x = 5`), the `UnknownName` error already fits without change. |
| Spec compliance | The spec only mandates the function-call error message; `UnknownName` is additive and does not conflict. |
| Implementation cost | One extra four-line class; no impact on other modules beyond `evaluator.py` raising it. |

`UnknownFunction` is raised by the evaluator when a `Call` node's `func` name is
not in `_FUNCTION_TABLE`. `UnknownName` is raised when a bare `Name` node's `name`
is not in `env`.

---

## 4. Class Hierarchy

```
Exception
└── CalcError                    (abstract base; description() -> str)
    ├── ExpectedSingleArg        (existing; no constructor args)
    ├── EmptyExpression          (existing; no constructor args)
    ├── UnexpectedToken          (existing; no constructor args)
    ├── UnexpectedEnd            (existing; no constructor args)
    ├── DivisionByZero           (existing; no constructor args)
    ├── Overflow                 (existing; no constructor args)
    ├── DomainError              (new v0.2.0; no constructor args)
    ├── UnknownFunction          (new v0.2.0; name: str)
    ├── WrongArity               (new v0.2.0; name: str, expected: int)
    └── UnknownName              (new v0.2.0; name: str)
```

---

## 5. Interface Specification

### 5.1 `CalcError`

```python
class CalcError(Exception):
    def description(self) -> str: ...  # abstract; subclasses must override
```

`CalcError` is not instantiated directly. The `description()` method has no
default implementation; any concrete subclass that omits it will cause
`error_message()` to raise `TypeError` (preserved guard, see §5.12).

### 5.2 `ExpectedSingleArg`

```python
class ExpectedSingleArg(CalcError):
    def description(self) -> str:
        return "expected a single quoted expression"
```

Raised in `__main__.main()` when `len(sys.argv) != 2`.

### 5.3 `EmptyExpression`

```python
class EmptyExpression(CalcError):
    def description(self) -> str:
        return "empty expression"
```

Raised in `__main__.main()` when `sys.argv[1].strip() == ""`.

### 5.4 `UnexpectedToken`

```python
class UnexpectedToken(CalcError):
    def description(self) -> str:
        return "unexpected token"
```

Raised by the lexer (unrecognised character) or parser (valid token in wrong
syntactic position).

### 5.5 `UnexpectedEnd`

```python
class UnexpectedEnd(CalcError):
    def description(self) -> str:
        return "unexpected end of expression"
```

Raised by the parser when EOF is encountered where an operand or token was
expected.

### 5.6 `DivisionByZero`

```python
class DivisionByZero(CalcError):
    def description(self) -> str:
        return "division by zero"
```

Raised by the evaluator when the right-hand operand of `/` evaluates to zero.

### 5.7 `Overflow`

```python
class Overflow(CalcError):
    def description(self) -> str:
        return "overflow"
```

Raised by the evaluator when the result is infinite or NaN, or when
`math.exp(large)` raises `OverflowError`.

### 5.8 `DomainError` (new)

```python
class DomainError(CalcError):
    def description(self) -> str:
        return "domain error"
```

Raised by the evaluator when a function argument is outside the function's
mathematical domain (e.g., `sqrt(-1)`, `log(-1)`, `log(0)`). Domain violations
are detected by explicit pre-checks in `FunctionEntry.domain_check`, not by
catching `ValueError` from `math.*`.

### 5.9 `UnknownFunction` (new)

```python
class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown function '{self.name}'"
```

Raised by the evaluator when a `Call` node's function name is not found in
`_FUNCTION_TABLE`.

### 5.10 `WrongArity` (new)

```python
class WrongArity(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.name = name
        self.expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        noun = "argument" if self.expected == 1 else "arguments"
        return f"'{self.name}' expects {self.expected} {noun}"
```

Raised by the evaluator when a `Call` node's argument count does not match
`FunctionEntry.arity`.

### 5.11 `UnknownName` (new)

```python
class UnknownName(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown name '{self.name}'"
```

Raised by the evaluator when a bare `Name` node is not found in `env`.

### 5.12 `error_message`

```python
def error_message(e: CalcError) -> str:
    if not hasattr(e, "description") or not callable(e.description):
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
    return f"error: {e.description()}"
```

**Alternative (simpler) implementation** — relies on Python's own `AttributeError`
or the abstract method being unimplemented:

```python
def error_message(e: CalcError) -> str:
    try:
        desc = e.description()
    except (AttributeError, NotImplementedError):
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}") from None
    return f"error: {desc}"
```

**Chosen approach:** The simplest correct implementation that preserves the
`TypeError` guard is to call `e.description()` directly and let a missing or
abstract `description` surface as `AttributeError`. Wrap this in a `try/except`
and re-raise as `TypeError` to match the existing test contract:

```python
def error_message(e: CalcError) -> str:
    try:
        return f"error: {e.description()}"
    except AttributeError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}") from None
```

This is simpler than `hasattr` + `callable` and correctly preserves the guard
that the existing `test_error_message_unknown_subclass` test relies on.

---

## 6. Migration from `_MESSAGES` dict

The existing `_MESSAGES` dict and its lookup in `error_message()` are removed.
Each existing subclass gains a `description()` body with the identical string it
previously had in `_MESSAGES`. No behaviour change for existing error paths.

| Class | Old `_MESSAGES` value | New `description()` return |
|-------|-----------------------|---------------------------|
| `ExpectedSingleArg` | `"expected a single quoted expression"` | same |
| `EmptyExpression` | `"empty expression"` | same |
| `UnexpectedToken` | `"unexpected token"` | same |
| `UnexpectedEnd` | `"unexpected end of expression"` | same |
| `DivisionByZero` | `"division by zero"` | same |
| `Overflow` | `"overflow"` | same |

---

## 7. Public API Summary

| Symbol | Kind | Notes |
|--------|------|-------|
| `CalcError` | class | base; `description()` abstract |
| `ExpectedSingleArg` | class | existing; no args |
| `EmptyExpression` | class | existing; no args |
| `UnexpectedToken` | class | existing; no args |
| `UnexpectedEnd` | class | existing; no args |
| `DivisionByZero` | class | existing; no args |
| `Overflow` | class | existing; no args |
| `DomainError` | class | new; no args |
| `UnknownFunction` | class | new; `name: str` |
| `WrongArity` | class | new; `name: str, expected: int` |
| `UnknownName` | class | new; `name: str` |
| `error_message` | function | `(CalcError) -> str`; raises `TypeError` for unregistered subclasses |

No other symbols are exported. `_MESSAGES` is removed entirely.

---

## 8. Dependencies

| Direction | Dependency |
|-----------|-----------|
| Imports | none (stdlib only) |
| Imported by | `evaluator.py`, `__main__.py`, `tests/test_errors.py`, `tests/test_cli.py` |

---

## 9. Test Plan (`tests/test_errors.py`)

All new tests are added to the existing `tests/test_errors.py` file.

### 9.1 Existing tests (must continue to pass unchanged)

| Test | Assertion |
|------|-----------|
| `test_error_message[ExpectedSingleArg]` | `error_message(ExpectedSingleArg()) == "error: expected a single quoted expression"` |
| `test_error_message[EmptyExpression]` | `error_message(EmptyExpression()) == "error: empty expression"` |
| `test_error_message[UnexpectedToken]` | `error_message(UnexpectedToken()) == "error: unexpected token"` |
| `test_error_message[UnexpectedEnd]` | `error_message(UnexpectedEnd()) == "error: unexpected end of expression"` |
| `test_error_message[DivisionByZero]` | `error_message(DivisionByZero()) == "error: division by zero"` |
| `test_error_message[Overflow]` | `error_message(Overflow()) == "error: overflow"` |
| `test_error_message_unknown_subclass` | `error_message(BogusError())` raises `TypeError` |
| `test_all_subclasses_inherit_from_calc_error` | all existing classes are `CalcError` subclasses |

### 9.2 New tests for v0.2.0

| Test | Assertion |
|------|-----------|
| `test_domain_error_message` | `error_message(DomainError()) == "error: domain error"` |
| `test_unknown_function_message` | `error_message(UnknownFunction("sqrt")) == "error: unknown function 'sqrt'"` |
| `test_wrong_arity_singular` | `error_message(WrongArity("abs", 1)) == "error: 'abs' expects 1 argument"` |
| `test_wrong_arity_plural` | `error_message(WrongArity("pow", 2)) == "error: 'pow' expects 2 arguments"` |
| `test_unknown_name_message` | `error_message(UnknownName("pi_approx")) == "error: unknown name 'pi_approx'"` |
| `test_new_subclasses_inherit_from_calc_error` | `DomainError`, `UnknownFunction`, `WrongArity`, `UnknownName` are all `CalcError` subclasses |
| `test_unknown_function_stores_name` | `UnknownFunction("foo").name == "foo"` |
| `test_wrong_arity_stores_fields` | `WrongArity("pow", 2).name == "pow"` and `.expected == 2` |
| `test_unknown_name_stores_name` | `UnknownName("x").name == "x"` |

Total new cases: ~9 (matches HLD estimate of ~7, slightly exceeded to cover field storage).

---

## 10. Error Message Strings (canonical)

| Class | `error_message(e)` output |
|-------|--------------------------|
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
| `UnknownName("x")` | `error: unknown name 'x'` |

---

## 11. Non-Goals

- No logging or tracing hooks inside error classes.
- No `__str__` override (Python's default `Exception.__str__` is sufficient for
  internal use; `error_message()` is the sole user-facing formatter).
- No chaining (`__cause__`/`__context__`) within `errors.py`; callers may use
  `raise X from Y` as they see fit.
