# Research: errors.py refactor migration — test_errors.py fixture compatibility and _MESSAGES removal

**Issue:** #68
**Milestone:** v0.2.0
**Date:** 2026-03-04

---

## Summary

The #55 refactor (replacing `_MESSAGES` dict with `description()` method dispatch) is safe to implement without modifying any existing test in `test_errors.py`. No existing message strings change. The TypeError guard is fully preserved. `__main__.py` requires no changes.

---

## Question 1: Does test_errors.py access `_MESSAGES` directly?

**No.** `tests/test_errors.py` imports only public symbols:

```python
from calc.errors import (
    CalcError,
    error_message,
    ExpectedSingleArg,
    EmptyExpression,
    UnexpectedToken,
    UnexpectedEnd,
    DivisionByZero,
    Overflow,
)
```

There is no reference to `_MESSAGES` anywhere in `tests/`. Removing the dict from `errors.py` breaks zero test assertions.

**Conclusion:** No test needs to be removed or updated due to `_MESSAGES` removal.

---

## Question 2: Is the TypeError guard preserved under NotImplementedError → TypeError re-raise?

The existing guard test is:

```python
def test_error_message_unknown_subclass():
    class BogusError(CalcError):
        pass

    with pytest.raises(TypeError):
        error_message(BogusError())
```

Under the #55 refactor, `CalcError.description()` raises `NotImplementedError`. `BogusError` does not override it. `error_message` becomes:

```python
def error_message(e: CalcError) -> str:
    try:
        return f"error: {e.description()}"
    except NotImplementedError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
```

Execution trace for `error_message(BogusError())`:
1. `BogusError().description()` → calls inherited `CalcError.description()` → raises `NotImplementedError`
2. `except NotImplementedError` catches it
3. `TypeError` is raised

`pytest.raises(TypeError)` catches the `TypeError`. **Test passes unchanged.**

**Conclusion:** The TypeError guard is fully preserved. Zero modification required.

---

## Question 3: Does `__main__.py` need any import or call-site changes?

`__main__.py` imports:

```python
from calc.errors import CalcError, ExpectedSingleArg, EmptyExpression, error_message
```

And calls `error_message(e)` in three places — all passing a `CalcError` instance. The `error_message` signature does not change (`e: CalcError) -> str`). All call sites are unaffected.

**Conclusion:** `__main__.py` requires zero changes.

---

## Question 4: Are all six existing error message strings reproduced verbatim?

Current `_MESSAGES` entries and the `description()` return values per the #55 interface sketch:

| Class | `_MESSAGES` value (v0.1.x) | `description()` return (v0.2.0) | Match |
|---|---|---|---|
| `ExpectedSingleArg` | `"expected a single quoted expression"` | `"expected a single quoted expression"` | ✓ |
| `EmptyExpression` | `"empty expression"` | `"empty expression"` | ✓ |
| `UnexpectedToken` | `"unexpected token"` | `"unexpected token"` | ✓ |
| `UnexpectedEnd` | `"unexpected end of expression"` | `"unexpected end of expression"` | ✓ |
| `DivisionByZero` | `"division by zero"` | `"division by zero"` | ✓ |
| `Overflow` | `"overflow"` | `"overflow"` | ✓ |

`error_message` wraps with `"error: "` in both versions. The `test_error_message` parametrize table asserts `"error: <description>"` — all six assertions remain valid.

**Conclusion:** All message strings are reproduced verbatim. Zero parametrize entries need modification.

---

## Complete impact matrix for test_errors.py

| Test | Status after #55 refactor | Action required |
|---|---|---|
| `test_error_message[ExpectedSingleArg-...]` | passes | none |
| `test_error_message[EmptyExpression-...]` | passes | none |
| `test_error_message[UnexpectedToken-...]` | passes | none |
| `test_error_message[UnexpectedEnd-...]` | passes | none |
| `test_error_message[DivisionByZero-...]` | passes | none |
| `test_error_message[Overflow-...]` | passes | none |
| `test_error_message_unknown_subclass` | passes | none |
| `test_all_subclasses_inherit_from_calc_error` | passes | none |

**All 8 tests pass without modification.**

---

## Lines that change in errors.py

The refactor touches `errors.py` only. Exact changes:

1. **Add `description()` to `CalcError`** — one method added to the base class.
2. **Add `description()` one-liner to each of the 6 existing subclasses** — 6 methods added.
3. **Remove `_MESSAGES` dict** — 9 lines deleted (dict definition + 6 entries + blank lines).
4. **Rewrite `error_message`** — dict lookup + `.get()` path replaced with `try/except NotImplementedError`.

No other file changes. Diff is entirely within `src/calc/errors.py`.

---

## Recommendation

Proceed with the #55 refactor immediately. It is a pure internal restructuring: the public API surface (`CalcError`, the six error classes, `error_message`) is unchanged, no test requires modification, and `__main__.py` is unaffected. The refactor unblocks `UnknownFunction` and `WrongArgCount` implementation for v0.2.0.
