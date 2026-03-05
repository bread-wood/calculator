# Low-Level Design — `errors` Module (v0.4.0)

**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Draft
**Issue:** #192

---

## 1. Responsibility

The `errors` module is the sole owner of the `CalcError` exception hierarchy. It
defines one base class and one concrete subclass per error variant, provides a
human-readable `description()` on each subclass, and exposes the `error_message()`
helper that formats the final stderr line. The module has **no dependencies** on any
other `calc` module, making it safe to import from any layer without creating a cycle.

---

## 2. Data Structures

### 2.1 `CalcError` — base class

```python
class CalcError(Exception):
    def description(self) -> str:
        raise AttributeError  # abstract; subclasses must override
```

- Inherits `Exception` so any `CalcError` is a native Python exception and can be
  raised and caught with standard syntax.
- `description()` is an abstract-by-convention method (no `@abstractmethod` decorator;
  the existing codebase uses `raise AttributeError` to signal missing overrides).
- Subclasses do **not** override `__str__`; the formatted message is always obtained
  by calling `description()` or `error_message()`.

### 2.2 Zero-argument error classes

These classes carry no per-instance data and require no `__init__` override. They
inherit `CalcError.__init__` unchanged.

| Class | `description()` return value |
|---|---|
| `ExpectedSingleArg` | `"expected a single quoted expression"` |
| `EmptyExpression` | `"empty expression"` |
| `UnexpectedToken` | `"unexpected token"` |
| `UnexpectedEnd` | `"unexpected end of expression"` |
| `DivisionByZero` | `"division by zero"` |
| `Overflow` | `"overflow"` |
| `DomainError` | `"domain error"` |

### 2.3 Parameterised error classes (pre-v0.4.0, updated in v0.4.0)

#### `UnknownFunction(name: str)` — message updated in v0.4.0

```python
class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined function: {self.name}"
```

Change from v0.3.x: prefix changed from `"unknown function '{name}'"` to
`"undefined function: {name}"` (drop surrounding quotes; change prefix word and
separator). No quotes around the name; consistent with `UndefinedVariable`.

#### `WrongArity(name: str, expected: int)` — message updated in v0.4.0

```python
class WrongArity(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.name = name
        self.expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        noun = "argument" if self.expected == 1 else "arguments"
        return f"wrong number of arguments: {self.name} expects {self.expected} {noun}"
```

Change from v0.3.x: prefix `"wrong number of arguments: "` added; surrounding
quotes around `name` removed. `expected` attribute is retained because it is
used by the pluralisation logic and may be inspected in tests.

#### `UndefinedVariable(name: str)` — unchanged

```python
class UndefinedVariable(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined variable: {self.name}"
```

#### `ConstantReassignment(name: str)` — unchanged

```python
class ConstantReassignment(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot reassign constant: {self.name}"
```

### 2.4 New parameterised error classes (v0.4.0)

#### `FunctionAlreadyDefined(name: str)`

```python
class FunctionAlreadyDefined(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"function already defined: {self.name}"
```

Raised by `execute_statement()` in the evaluator when a `FunctionDef` statement
names a function already present in `fn_env`. This is a user-defined → user-defined
collision. It is **not** a subclass of `CannotRedefineBuiltin`; the two conditions
are semantically distinct.

#### `CannotRedefineBuiltin(name: str)`

```python
class CannotRedefineBuiltin(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot redefine built-in: {self.name}"
```

Raised by `execute_statement()` when a `FunctionDef` targets a name that already
exists in `_FUNCTION_TABLE` (the built-in function registry). It is a **sibling** of
`FunctionAlreadyDefined` (both are direct subclasses of `CalcError`), enabling
unambiguous `isinstance` checks in tests.

### 2.5 Class hierarchy diagram

```
CalcError (Exception)
├── ExpectedSingleArg
├── EmptyExpression
├── UnexpectedToken
├── UnexpectedEnd
├── DivisionByZero
├── Overflow
├── DomainError
├── UnknownFunction          (message updated v0.4.0)
├── WrongArity               (message updated v0.4.0)
├── UndefinedVariable
├── ConstantReassignment
├── FunctionAlreadyDefined   (NEW v0.4.0)
└── CannotRedefineBuiltin    (NEW v0.4.0)
```

All subclasses are direct children of `CalcError`. No intermediate abstract classes
are introduced.

---

## 3. Public API / Interfaces

### 3.1 Module-level exports

`errors.py` exposes every class listed in §2 and the `error_message()` helper. There
is no `__all__`; all top-level names are importable.

### 3.2 `error_message(e: CalcError) -> str`

```python
def error_message(e: CalcError) -> str:
    try:
        return f"error: {e.description()}"
    except AttributeError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}") from None
```

- Produces the exact string written to stderr by the CLI (`"error: <description>"`).
- Guards against subclasses that forget to override `description()` by converting
  the `AttributeError` into a `TypeError` with a diagnostic message.
- No change to this function in v0.4.0.

### 3.3 Raise-site responsibility

The `errors` module only **defines** exceptions; it never raises them itself.
Raise-site responsibility by class:

| Class | Module that raises it |
|---|---|
| `ExpectedSingleArg` | `cli` (`__main__.py`) |
| `EmptyExpression` | `cli` (`__main__.py`) |
| `UnexpectedToken` | `lexer.py`, `parser.py` |
| `UnexpectedEnd` | `parser.py` |
| `DivisionByZero` | `evaluator.py` |
| `Overflow` | `evaluator.py` |
| `DomainError` | `evaluator.py` |
| `UnknownFunction` | `evaluator.py` (built-in dispatch + definition-time body walk) |
| `WrongArity` | `evaluator.py` |
| `UndefinedVariable` | `evaluator.py` |
| `ConstantReassignment` | `evaluator.py` |
| `FunctionAlreadyDefined` | `evaluator.py` (`execute_statement`) |
| `CannotRedefineBuiltin` | `evaluator.py` (`execute_statement`) |

---

## 4. Key Algorithms

The `errors` module contains no algorithms; it is pure data definitions. The only
non-trivial logic is in `WrongArity.description()`:

```python
noun = "argument" if self.expected == 1 else "arguments"
return f"wrong number of arguments: {self.name} expects {self.expected} {noun}"
```

This is a single conditional expression for English pluralisation. It is applied
uniformly for both built-in and user-defined function arity mismatches.

---

## 5. Error Handling

The `errors` module itself raises only one exception type: `TypeError` from
`error_message()` when the supplied `CalcError` subclass has not overridden
`description()`. This is a programming error (not a user error) and is never caught
at the CLI boundary.

All other error conditions in the system are handled by:
1. A subclass of `CalcError` being raised at the appropriate layer.
2. The CLI catching the first `CalcError` that propagates to it, calling
   `error_message(e)`, writing the result to stderr, and exiting with code 1.

No error is swallowed silently anywhere in the pipeline.

---

## 6. File Layout

```
src/calc/errors.py
```

Single file, no subpackages. Ordering of class definitions in the file:

1. `CalcError` (base)
2. Zero-argument classes in their existing order:
   `ExpectedSingleArg`, `EmptyExpression`, `UnexpectedToken`, `UnexpectedEnd`,
   `DivisionByZero`, `Overflow`, `DomainError`
3. Parameterised classes (existing, in their existing order):
   `UnknownFunction`, `WrongArity`, `UndefinedVariable`, `ConstantReassignment`
4. New parameterised classes (appended at end):
   `FunctionAlreadyDefined`, `CannotRedefineBuiltin`
5. `error_message()` helper (last, as today)

Adding new classes at the end of the file avoids unnecessary diff noise on existing
lines and keeps git blame clean.

---

## 7. Test Strategy

Tests live in `tests/test_errors.py`. A `# v0.4.0 — user-defined functions` block
is appended to the existing file.

### 7.1 Tests to update (existing assertions)

| Test function | Required change |
|---|---|
| `test_unknown_function_message` | Expected string: `"error: undefined function: sqrt"` (was `"error: unknown function 'sqrt'"`) |
| `test_wrong_arity_singular` | Expected string: `"error: wrong number of arguments: abs expects 1 argument"` (was `"error: 'abs' expects 1 argument"`) |
| `test_wrong_arity_plural` | Expected string: `"error: wrong number of arguments: pow expects 2 arguments"` (was `"error: 'pow' expects 2 arguments"`) |

### 7.2 New tests

```python
# v0.4.0 — user-defined functions

def test_function_already_defined_message():
    assert error_message(FunctionAlreadyDefined("f")) == "error: function already defined: f"

def test_cannot_redefine_builtin_message():
    assert error_message(CannotRedefineBuiltin("sqrt")) == "error: cannot redefine built-in: sqrt"

def test_unknown_function_no_quotes():
    """Name must not be surrounded by quotes in the new wording."""
    msg = error_message(UnknownFunction("myFunc"))
    assert "'" not in msg
    assert "myFunc" in msg

def test_wrong_arity_no_quotes_around_name():
    """Function name must not be surrounded by quotes in the new wording."""
    msg = error_message(WrongArity("myFunc", 2))
    assert "'" not in msg
    assert "myFunc" in msg

def test_wrong_arity_new_prefix():
    assert error_message(WrongArity("f", 1)).startswith("error: wrong number of arguments:")

def test_function_already_defined_stores_name():
    e = FunctionAlreadyDefined("g")
    assert e.name == "g"

def test_cannot_redefine_builtin_stores_name():
    e = CannotRedefineBuiltin("sin")
    assert e.name == "sin"

def test_function_already_defined_is_calc_error():
    assert isinstance(FunctionAlreadyDefined("f"), CalcError)

def test_cannot_redefine_builtin_is_calc_error():
    assert isinstance(CannotRedefineBuiltin("sin"), CalcError)

def test_function_already_defined_not_subclass_of_cannot_redefine():
    assert not issubclass(FunctionAlreadyDefined, CannotRedefineBuiltin)

def test_cannot_redefine_not_subclass_of_function_already_defined():
    assert not issubclass(CannotRedefineBuiltin, FunctionAlreadyDefined)
```

### 7.3 Test coverage targets

- Every `CalcError` subclass must have at least one test asserting the exact string
  returned by `error_message()`.
- `WrongArity` must have tests for both singular (`expected=1`) and plural
  (`expected=2`) forms.
- The two new sibling classes (`FunctionAlreadyDefined`, `CannotRedefineBuiltin`)
  must each have a test asserting `isinstance(e, CalcError)` and a test asserting
  they are **not** subclasses of each other.
- `error_message()` itself is covered implicitly by all class-level tests; no
  additional integration test needed.

### 7.4 What is not tested here

Raise-sites (the evaluator calling `raise FunctionAlreadyDefined(name)`) are tested
in `test_evaluator.py` and `test_cli.py`, not in `test_errors.py`. The `errors`
module tests focus solely on the description strings and class relationships.

---

## 8. Open Questions Resolved

From HLD §Open Questions item 4:

> **`errors` LLD** — Whether `WrongArity` retains a separate `expected` attribute
> after the message change, and whether `CannotRedefineBuiltin` is a subclass of
> any existing error or a direct subclass of `CalcError`.

**Resolved:**

- `WrongArity.expected` is retained. It is required by the pluralisation logic
  inside `description()` and may be inspected by test code asserting on the numeric
  value without parsing the message string.
- `CannotRedefineBuiltin` is a **direct subclass of `CalcError`**, not a subclass
  of `FunctionAlreadyDefined` or any other error. This keeps `isinstance` checks
  unambiguous and reflects the semantic distinction: shadowing a built-in is a
  different user mistake from redefining a previously user-defined function.
