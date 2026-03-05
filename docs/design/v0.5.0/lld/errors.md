# Low-Level Design — Module: errors (v0.5.0)

**Milestone:** v0.5.0
**Issue:** #221
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

`src/calc/errors.py` defines the complete `CalcError` exception hierarchy used across
all pipeline stages. Every error that results in a stderr message and exit 1 is a
`CalcError` subclass. No other module defines user-visible error classes.

---

## 2. Data Structures

### 2.1 Abstract Base Class

```python
class CalcError(Exception):
    """Base class for all calculator errors."""

    def description(self) -> str:
        """Return the bare error message (no 'error: ' prefix)."""
        raise NotImplementedError
```

`CalcError` is not instantiated directly. Every concrete subclass must override
`description()`. The `super().__init__(...)` call is made with the primary dynamic
argument (if any), allowing `str(e)` to produce a usable string from the exception
object for debugging.

### 2.2 Module-level helper

```python
def error_message(e: CalcError) -> str:
    return f"error: {e.description()}"
```

Signature unchanged from v0.4.x. All new classes follow the existing contract;
no changes to this function are required.

---

## 3. Public API / Interfaces

### 3.1 Expression-evaluation error classes (v0.1.x–v0.4.x, unchanged)

| Class | Constructor | `description()` |
|---|---|---|
| `ExpectedSingleArg` | `()` | `expected a single quoted expression` |
| `EmptyExpression` | `()` | `empty expression` |
| `UnexpectedToken` | `()` | `unexpected token` |
| `UnexpectedEnd` | `()` | `unexpected end of expression` |
| `DivisionByZero` | `()` | `division by zero` |
| `Overflow` | `()` | `overflow` |
| `DomainError` | `()` | `domain error` |
| `UnknownFunction(name)` | `(name: str)` | `unknown function '{name}'` |
| `WrongArity(name, n)` | `(name: str, n: int)` | `'{name}' expects {n} argument(s)` |
| `UndefinedVariable(name)` | `(name: str)` | `undefined variable: {name}` |
| `ConstantReassignment(name)` | `(name: str)` | `cannot reassign constant: {name}` |
| `FunctionAlreadyDefined(name)` | `(name: str)` | *(existing format)* |
| `CannotRedefineBuiltin(name)` | `(name: str)` | *(existing format)* |

None of these classes are modified in v0.5.0.

### 3.2 Plot-path error classes (new in v0.5.0)

All five new classes are added to `src/calc/errors.py` as siblings at module level.
They are direct subclasses of `CalcError` (not of each other or of any existing
subclass).

#### `UndefinedFunction`

```python
class UndefinedFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined function: {self.name}"
```

- **Raised by:** `run_plot` in `__main__.py`, which catches `UnknownFunction` from the
  evaluator and re-raises as `UndefinedFunction`.
- **`description()` output:** `undefined function: <name>` (colon separator, no
  quotes). This is intentionally different from `UnknownFunction` to match the v0.5.0
  spec without breaking existing tests.
- **`super().__init__`:** called with `name` so `str(e)` returns the function name.

#### `OutputWriteError`

```python
class OutputWriteError(CalcError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def description(self) -> str:
        return f"cannot write output: {self.reason}"
```

- **Raised by:** `run_plot` when an `OSError` is caught from the renderer:
  ```python
  except OSError as e:
      raise OutputWriteError(str(e)) from e
  ```
- **`description()` output:** `cannot write output: <reason>` where `<reason>` is
  `str(the_os_error)`.
- **`super().__init__`:** called with `reason`.

#### `UnsupportedFormat`

```python
class UnsupportedFormat(CalcError):
    def __init__(self, ext: str) -> None:
        self.ext = ext
        super().__init__(ext)

    def description(self) -> str:
        return f"unsupported format: {self.ext}; use .png or .svg"
```

- **Raised by:** `run_plot` during CLI argument validation, before any parsing or
  rendering work:
  ```python
  if output.suffix not in {".png", ".svg"}:
      raise UnsupportedFormat(output.suffix)
  ```
- **`description()` output:** `unsupported format: <ext>; use .png or .svg` where
  `<ext>` is `Path(output).suffix` (e.g., `.bmp`).
- **`super().__init__`:** called with `ext`.

#### `DomainEmpty`

```python
class DomainEmpty(CalcError):
    def description(self) -> str:
        return "expression undefined over entire domain"
```

- **Raised by:** `plotter.build_scene` after sampling, when zero valid (non-`None`)
  sample points remain across all segments.
- **`description()` output:** `expression undefined over entire domain` (fixed string,
  no dynamic component).
- **`super().__init__`:** not called explicitly; `Exception.__init__()` default is
  sufficient.

#### `InvalidDomainBounds`

```python
class InvalidDomainBounds(CalcError):
    def description(self) -> str:
        return "xmin must be less than xmax"
```

- **Raised by:** `run_plot` during CLI argument validation:
  ```python
  if args.xmin >= args.xmax:
      raise InvalidDomainBounds()
  ```
- **`description()` output:** `xmin must be less than xmax` (fixed string).
- **`super().__init__`:** not called explicitly.

---

## 4. Key Algorithms

This module contains no algorithmic logic. All behaviour is pure data-class construction
and string formatting in `description()` methods.

---

## 5. Error Handling

`errors.py` is the error-definition layer; it does not itself raise or catch errors.
The caller contract is:

1. Any pipeline stage raises a `CalcError` subclass on failure.
2. The top-level handler in `__main__.py` catches `CalcError`, calls
   `error_message(e)`, writes to `sys.stderr`, and exits 1.
3. `OSError` from the renderer is wrapped into `OutputWriteError` in `run_plot` before
   it reaches the top-level handler; no `OSError` escapes to the user.

**`UndefinedFunction` vs `UnknownFunction` protocol:**

`run_plot` catches `UnknownFunction` (raised by the evaluator) and re-raises as
`UndefinedFunction`:

```python
except UnknownFunction as e:
    raise UndefinedFunction(e.name) from e
```

This keeps the evaluator untouched and ensures the plot path emits the spec-mandated
format. A follow-up issue will decide whether to consolidate the two classes.

---

## 6. File Layout

```
src/calc/errors.py
```

Single file. All classes — both existing (v0.1.x–v0.4.x) and new (v0.5.0) — live in
this one module. No sub-package split is introduced in v0.5.0.

**Order of class definitions in the file:**

1. `CalcError` (base)
2. `error_message` (helper function)
3. Existing expression-error classes (unchanged, in their current order)
4. New v0.5.0 plot-error classes: `UndefinedFunction`, `OutputWriteError`,
   `UnsupportedFormat`, `DomainEmpty`, `InvalidDomainBounds`

The new classes are appended after the existing ones to minimise diff noise and avoid
any import-order sensitivity.

---

## 7. Dependencies

`errors.py` has **no imports**. It depends on nothing — not even `abc` — because
`description()` is implemented as a regular method that raises `NotImplementedError`
in the base class rather than using `@abstractmethod`.

---

## 8. Test Strategy

**Test file:** `tests/test_errors.py` (extended from v0.4.x)

### 8.1 Tests for existing classes (regression, unchanged)

No new test cases are added for v0.1.x–v0.4.x error classes. All existing assertions
continue to pass.

### 8.2 Tests for new v0.5.0 classes

One test function per new class. Each test verifies:

1. The class is a subclass of `CalcError`.
2. `description()` returns the exact expected string.
3. `error_message(e)` returns `"error: " + description`.
4. `str(e)` returns the primary dynamic argument (where applicable).

#### `UndefinedFunction`

```python
def test_undefined_function():
    e = UndefinedFunction("foo")
    assert isinstance(e, CalcError)
    assert e.description() == "undefined function: foo"
    assert error_message(e) == "error: undefined function: foo"
    assert str(e) == "foo"
```

#### `OutputWriteError`

```python
def test_output_write_error():
    e = OutputWriteError("Permission denied: '/root/plot.png'")
    assert isinstance(e, CalcError)
    assert e.description() == "cannot write output: Permission denied: '/root/plot.png'"
    assert error_message(e) == "error: cannot write output: Permission denied: '/root/plot.png'"
    assert str(e) == "Permission denied: '/root/plot.png'"
```

#### `UnsupportedFormat`

```python
def test_unsupported_format():
    e = UnsupportedFormat(".bmp")
    assert isinstance(e, CalcError)
    assert e.description() == "unsupported format: .bmp; use .png or .svg"
    assert error_message(e) == "error: unsupported format: .bmp; use .png or .svg"
    assert str(e) == ".bmp"
```

#### `DomainEmpty`

```python
def test_domain_empty():
    e = DomainEmpty()
    assert isinstance(e, CalcError)
    assert e.description() == "expression undefined over entire domain"
    assert error_message(e) == "error: expression undefined over entire domain"
```

#### `InvalidDomainBounds`

```python
def test_invalid_domain_bounds():
    e = InvalidDomainBounds()
    assert isinstance(e, CalcError)
    assert e.description() == "xmin must be less than xmax"
    assert error_message(e) == "error: xmin must be less than xmax"
```

### 8.3 `UndefinedFunction` vs `UnknownFunction` isolation test

```python
def test_undefined_function_is_not_unknown_function():
    assert not issubclass(UndefinedFunction, UnknownFunction)
    assert not issubclass(UnknownFunction, UndefinedFunction)
```

Ensures the two classes remain independent so that a `except UnknownFunction` handler
does not accidentally catch `UndefinedFunction` or vice versa.

### 8.4 Coverage targets

- All five new classes: 100% line coverage.
- `error_message()`: already covered by existing tests; new tests add additional calls.
- No integration tests in `test_errors.py`; integration coverage (e.g., CLI exit code
  1 + correct stderr) lives in `tests/test_plot.py`.

---

## 9. Open Question Resolution

**HLD open question 4:** "Whether `UndefinedFunction` is a sibling of `UnknownFunction`
or a subclass; exact `super().__init__` call signature for the new error classes."

**Resolution:**
- `UndefinedFunction` is a **direct subclass of `CalcError`**, not a subclass of
  `UnknownFunction`. This prevents a `except UnknownFunction` handler from accidentally
  catching `UndefinedFunction`.
- `super().__init__` for parameterised classes (`UndefinedFunction`, `OutputWriteError`,
  `UnsupportedFormat`) is called with the primary string argument so that `str(e)`
  returns something meaningful.
- `DomainEmpty` and `InvalidDomainBounds` have no parameters and do not call
  `super().__init__` explicitly (the `Exception` default takes no positional args and
  is harmless).
