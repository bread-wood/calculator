# Low-Level Design — Module: errors

**Milestone:** v0.1.0
**Date:** 2026-03-04
**Status:** Draft
**File:** `src/calc/errors.py`

---

## 1. Responsibility

Define the `CalcError` exception hierarchy and the canonical error-message mapping used by all layers of the calculator pipeline. No other module owns error strings; all layers raise `CalcError` subclasses and propagate them to `__main__.py`, which is the sole writer to stderr.

---

## 2. Data Structures

### 2.1 Exception Hierarchy

```
CalcError(Exception)
├── ExpectedSingleArg
├── EmptyExpression
├── UnexpectedToken
├── UnexpectedEnd
├── DivisionByZero
└── Overflow
```

All subclasses inherit from `CalcError` with no additional attributes in v0.1.0. The base class stores no state beyond Python's built-in `Exception` machinery.

### 2.2 Class Definitions

```python
class CalcError(Exception):
    """Base class for all calculator errors."""

class ExpectedSingleArg(CalcError):
    """Raised when argument count != 1 (and != 0, which yields usage)."""

class EmptyExpression(CalcError):
    """Raised when argv[1] is the empty string."""

class UnexpectedToken(CalcError):
    """Raised by lexer (unrecognised character) or parser (valid token in wrong position)."""

class UnexpectedEnd(CalcError):
    """Raised by parser when EOF is encountered where an operand/token was expected."""

class DivisionByZero(CalcError):
    """Raised by evaluator when the right-hand operand of '/' evaluates to zero."""

class Overflow(CalcError):
    """Raised by evaluator when the result is infinite or NaN."""
```

### 2.3 Error Message Map

```python
_MESSAGES: dict[type[CalcError], str] = {
    ExpectedSingleArg: "expected a single quoted expression",
    EmptyExpression:   "empty expression",
    UnexpectedToken:   "unexpected token",
    UnexpectedEnd:     "unexpected end of expression",
    DivisionByZero:    "division by zero",
    Overflow:          "overflow",
}
```

---

## 3. Public API

### `error_message(e: CalcError) -> str`

Returns the verbatim `error: <description>` string for the given exception instance.

```python
def error_message(e: CalcError) -> str:
    description = _MESSAGES.get(type(e))
    if description is None:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
    return f"error: {description}"
```

**Contract:**
- Input: any instance of a known `CalcError` subclass.
- Output: a string of the form `"error: <description>"` with no trailing newline.
- Raises `TypeError` if called with an unknown subclass (programming error, not user error).
- This is the **only** place error description strings appear in the codebase (DRY).

---

## 4. Key Algorithms

There are no non-trivial algorithms in this module. The entire logic is a dict lookup keyed on the concrete exception type.

**Lookup strategy:** `type(e)` is used (not `isinstance`) to ensure each subclass maps to exactly one message. If a future subclass of `UnexpectedToken` is introduced, it will trigger the `TypeError` guard and require an explicit entry in `_MESSAGES`, preventing silent message inheritance.

---

## 5. Error Handling Within This Module

- `error_message` itself does not raise `CalcError`; it raises `TypeError` only on programmer error (unregistered subclass).
- No I/O, no side effects, no mutable state.

---

## 6. Interaction with Other Modules

| Caller | Raises | Via |
|---|---|---|
| `__main__.py` | `ExpectedSingleArg`, `EmptyExpression` | arg-count / empty-string checks |
| `lexer.py` | `UnexpectedToken` | unrecognised character |
| `parser.py` | `UnexpectedToken`, `UnexpectedEnd` | syntax errors |
| `evaluator.py` | `DivisionByZero`, `Overflow` | arithmetic errors |
| `__main__.py` | — | catches all `CalcError`; calls `error_message(e)` |

All modules import from `errors.py`. `errors.py` imports nothing from any other calc module.

---

## 7. Test Strategy

**File:** `tests/test_errors.py`

### 7.1 Unit Tests

| Test | Assertion |
|---|---|
| `error_message(ExpectedSingleArg())` | `== "error: expected a single quoted expression"` |
| `error_message(EmptyExpression())` | `== "error: empty expression"` |
| `error_message(UnexpectedToken())` | `== "error: unexpected token"` |
| `error_message(UnexpectedEnd())` | `== "error: unexpected end of expression"` |
| `error_message(DivisionByZero())` | `== "error: division by zero"` |
| `error_message(Overflow())` | `== "error: overflow"` |
| `error_message(CalcError())` | raises `TypeError` |
| Each subclass `issubclass(X, CalcError)` | `True` for all 6 subclasses |

### 7.2 Integration Role

CLI integration tests (`tests/test_cli.py`) assert exact stderr strings using `subprocess.run`. Those assertions are cross-checked against `error_message()` return values to guarantee the integration tests never diverge from the canonical strings defined in this module.

### 7.3 Test Parameterization

```python
import pytest
from calc.errors import (
    CalcError, error_message,
    ExpectedSingleArg, EmptyExpression, UnexpectedToken,
    UnexpectedEnd, DivisionByZero, Overflow,
)

@pytest.mark.parametrize("exc_cls,expected", [
    (ExpectedSingleArg, "error: expected a single quoted expression"),
    (EmptyExpression,   "error: empty expression"),
    (UnexpectedToken,   "error: unexpected token"),
    (UnexpectedEnd,     "error: unexpected end of expression"),
    (DivisionByZero,    "error: division by zero"),
    (Overflow,          "error: overflow"),
])
def test_error_message(exc_cls, expected):
    assert error_message(exc_cls()) == expected

def test_error_message_unknown_subclass():
    class BogusError(CalcError): pass
    with pytest.raises(TypeError):
        error_message(BogusError())
```

---

## 8. Non-Goals (v0.1.0)

- No `(line, col, offset)` payload on variants — additive in a future version.
- No distinct exit codes per error class — exit codes (0/1) are owned by `__main__.py`.
- No i18n / localisation of message strings.
- No logging or debug output.

---

## 9. Future Extension Points

- Adding source-location info: give each subclass an optional `offset: int | None = None` field; `error_message` can include it in the string when present without breaking existing call sites.
- Distinct exit codes: `__main__.py` can `match type(e)` on the variant without any change to this module.
