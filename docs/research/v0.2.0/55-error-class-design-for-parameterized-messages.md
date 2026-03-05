# Research: Error Class Design for Parameterized Messages

**Issue:** #55
**Milestone:** v0.2.0
**Date:** 2026-03-04

---

## Background

`errors.py` currently maps `type(e) → str` via `_MESSAGES: dict[type[CalcError], str]`.
This is sufficient for v0.1.x because every error message is static.

v0.2.0 introduces three new error conditions:

| Condition | Message | Runtime data? |
|---|---|---|
| Unknown function call | `error: unknown function: <name>` | yes — function name |
| Wrong argument count | `error: wrong number of arguments: <name> expects <N>` | yes — name + count |
| Domain error (e.g. sqrt(-1)) | `error: domain error` | no |

The first two require values that are only known at raise time, so the static dict cannot express them.

---

## Options Evaluated

### Option A — message-on-construction

Store the formatted string in the instance at construction time:

```python
class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.message = f"unknown function: {name}"
        super().__init__(self.message)

class WrongArgCount(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.message = f"wrong number of arguments: {name} expects {expected}"
        super().__init__(self.message)
```

`error_message` would need a special-case branch or a fallback to `e.message`:

```python
def error_message(e: CalcError) -> str:
    description = _MESSAGES.get(type(e))
    if description is None:
        if hasattr(e, "message"):
            return f"error: {e.message}"
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
    return f"error: {description}"
```

**Problems:**
- Mixes two dispatch strategies (`_MESSAGES` dict + `hasattr` duck-typing).
- `hasattr(e, "message")` silently accepts any future unregistered subclass that happens to define `.message`, bypassing the TypeError guard.
- The TypeError guard — tested explicitly in `test_error_message_unknown_subclass` — is weakened: a `BogusError` that sets `self.message` would silently pass through.
- `_MESSAGES` is left as a half-useful artifact; the "authority" of the registry is split.

### Option B — `description()` method override (recommended)

Replace the `_MESSAGES` dict entirely with a `description() -> str` method on `CalcError`:

```python
class CalcError(Exception):
    def description(self) -> str:
        raise NotImplementedError  # forces every subclass to implement

class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self._name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown function: {self._name}"

class WrongArgCount(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self._name = name
        self._expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        return f"wrong number of arguments: {self._name} expects {self._expected}"

class DomainError(CalcError):
    def description(self) -> str:
        return "domain error"

# Existing static classes get a one-liner:
class DivisionByZero(CalcError):
    def description(self) -> str:
        return "division by zero"
```

`error_message` becomes:

```python
def error_message(e: CalcError) -> str:
    if not isinstance(e, CalcError):
        raise TypeError(f"Not a CalcError: {type(e)!r}")
    try:
        return f"error: {e.description()}"
    except NotImplementedError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
```

**Advantages:**
- Single, uniform dispatch path — every class carries its own message logic.
- No mixed strategies; `_MESSAGES` is removed entirely.
- Parameterized data (name, N) is stored on the instance, keeping it accessible for callers that need it (e.g. tests, future error recovery).
- `DomainError` is trivially handled — its `description()` returns a fixed string, identical pattern to `DivisionByZero`.
- Extensible: new error types never require touching `error_message` or `_MESSAGES`.

**Impact on `test_errors.py`:**
- `test_error_message` calls `exc_cls()` with no arguments for static errors. Those classes keep zero-arg constructors, so the parametrize table is unchanged.
- `test_error_message_unknown_subclass` relies on `TypeError` being raised for an unknown subclass. With Option B the base `CalcError.description()` raises `NotImplementedError`, which `error_message` catches and re-raises as `TypeError` — preserving the contract exactly.
- New test cases for `UnknownFunction` and `WrongArgCount` will call `exc_cls(name, n)` with appropriate args; they fit naturally into the same parametrize table as separate entries.

### Option C — keep dict, add isinstance branch

```python
def error_message(e: CalcError) -> str:
    description = _MESSAGES.get(type(e))
    if description is None:
        if isinstance(e, UnknownFunction):
            return f"error: unknown function: {e.name}"
        if isinstance(e, WrongArgCount):
            return f"error: wrong number of arguments: {e.name} expects {e.expected}"
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
    return f"error: {description}"
```

**Problems:**
- Every new parameterized error type requires a new `isinstance` branch in `error_message` — violating open/closed.
- `error_message` accumulates knowledge about individual subclasses; the function grows unbounded.
- Produces the smallest diff for v0.2.0 but becomes the worst option as more error types are added in later milestones.

---

## Recommendation: Option B

Option B is consistent with the existing design's intent (each `CalcError` subclass is the authority for its own semantics), removes an awkward external registry, and handles all three new error types — including the fully static `DomainError` — with zero special-cases in `error_message`.

---

## `DomainError` — stored fields?

`DomainError` carries no runtime data. Its message is always `"domain error"`, identical in structure to `DivisionByZero` or `Overflow`. No stored fields are needed; `description()` is a plain one-liner. The failing value (e.g. `-1` passed to `sqrt`) does not appear in the user-facing message, so there is no reason to store it on the instance (though a future debug/verbose mode could add it without changing the interface).

---

## Interface Sketch

```python
# errors.py — v0.2.0 interface

class CalcError(Exception):
    """Base class for all calculator errors."""
    def description(self) -> str:
        raise NotImplementedError


# --- existing static errors (unchanged behaviour, new one-liner method) ---

class ExpectedSingleArg(CalcError):
    def description(self) -> str: return "expected a single quoted expression"

class EmptyExpression(CalcError):
    def description(self) -> str: return "empty expression"

class UnexpectedToken(CalcError):
    def description(self) -> str: return "unexpected token"

class UnexpectedEnd(CalcError):
    def description(self) -> str: return "unexpected end of expression"

class DivisionByZero(CalcError):
    def description(self) -> str: return "division by zero"

class Overflow(CalcError):
    def description(self) -> str: return "overflow"


# --- new v0.2.0 errors ---

class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown function: {self.name}"


class WrongArgCount(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.name = name
        self.expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        return f"wrong number of arguments: {self.name} expects {self.expected}"


class DomainError(CalcError):
    def description(self) -> str: return "domain error"


# --- dispatcher (replaces _MESSAGES dict) ---

def error_message(e: CalcError) -> str:
    """Return the user-facing error string for a CalcError instance.

    Raises TypeError for any CalcError subclass that has not implemented
    description(), preserving the existing unknown-subclass contract.
    """
    try:
        return f"error: {e.description()}"
    except NotImplementedError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
```

**Signature change summary:**

| Symbol | v0.1.x | v0.2.0 |
|---|---|---|
| `CalcError` | bare `Exception` subclass | adds abstract `description() -> str` |
| `_MESSAGES` | module-level dict | removed |
| `error_message(e)` | dict lookup + TypeError | calls `e.description()` + TypeError on `NotImplementedError` |
| `UnknownFunction` | new | `__init__(name: str)` |
| `WrongArgCount` | new | `__init__(name: str, expected: int)` |
| `DomainError` | new | no-arg, static description |

The `error_message` signature itself (`e: CalcError) -> str`) is unchanged; all call sites are unaffected.
