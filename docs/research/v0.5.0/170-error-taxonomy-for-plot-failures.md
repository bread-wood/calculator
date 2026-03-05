# Research: Error Taxonomy for Plot-Specific Failures

**Issue:** #170
**Milestone:** v0.5.0
**Date:** 2026-03-05

---

## 1. Existing Error Infrastructure Audit

### 1.1 `error_message()` contract

```python
def error_message(e: CalcError) -> str:
    return f"error: {e.description()}"
```

Every `CalcError` subclass implements `description() -> str` which returns the bare message (without the `error: ` prefix). The caller prints to stderr and exits 1.

### 1.2 Existing subclasses and their `description()` output

| Class | `description()` output |
|---|---|
| `ExpectedSingleArg` | `expected a single quoted expression` |
| `EmptyExpression` | `empty expression` |
| `UnexpectedToken` | `unexpected token` |
| `UnexpectedEnd` | `unexpected end of expression` |
| `DivisionByZero` | `division by zero` |
| `Overflow` | `overflow` |
| `DomainError` | `domain error` |
| `UnknownFunction(name)` | `unknown function '{name}'` (note: single-quoted name) |
| `WrongArity(name, n)` | `'{name}' expects {n} argument(s)` |
| `UndefinedVariable(name)` | `undefined variable: {name}` |
| `ConstantReassignment(name)` | `cannot reassign constant: {name}` |

---

## 2. Spec Error Messages vs. Existing Classes

### 2.1 Message-format discrepancy table

| Spec error string | Existing class | Existing `description()` | Discrepancy? |
|---|---|---|---|
| `error: undefined function: <name>` | `UnknownFunction` | `unknown function '{name}'` | **YES** — spec uses `undefined function: <name>` (colon-separated, no quotes); existing uses `unknown function '<name>'` (space-separated, single-quoted) |
| `error: undefined variable: <name>` | `UndefinedVariable` | `undefined variable: {name}` | **None** — formats match exactly |
| `error: cannot write output: <reason>` | — | — | New; no existing class |
| `error: unsupported format: <ext>; use .png or .svg` | — | — | New; no existing class |
| `error: expression undefined over entire domain` | — | — | New; no existing class |
| `error: xmin must be less than xmax` | — | — | New; no existing class |

### 2.2 Breaking-change assessment

- **`undefined variable: <name>`**: zero breaking change — `UndefinedVariable.description()` already matches.
- **`undefined function: <name>`**: **breaking change** if `UnknownFunction.description()` is modified. Current output is `unknown function '<name>'`; spec requires `undefined function: <name>`. These differ in three ways: the verb (`unknown` → `undefined`), the separator (space → colon), and the quoting (single quotes dropped). Existing tests that match the string `unknown function` will fail. A new subclass avoids breaking existing tests.

---

## 3. Mapping Each Spec Error to Its Implementation Path

### 3.1 `error: undefined function: <name>`

**Recommendation: new subclass `UndefinedFunction` in `errors.py`.**

Rationale:
- `UnknownFunction` is already tested with format `unknown function '<name>'`; changing it is a breaking change.
- The plot command is the first consumer to use the spec-mandated format `undefined function: <name>`. The evaluator currently raises `UnknownFunction`; the plot command can either re-raise as `UndefinedFunction` or the plot evaluator path can raise `UndefinedFunction` directly.
- Longer-term both names may coexist until a separate refactor aligns the calc subcommand format.

```python
class UndefinedFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"undefined function: {self.name}"
```

### 3.2 `error: undefined variable: <name>`

**Recommendation: reuse existing `UndefinedVariable` — no change needed.**

`UndefinedVariable.description()` already returns `undefined variable: {name}` which matches the spec exactly. The plot path can raise this class directly.

### 3.3 `error: cannot write output: <reason>`

**Recommendation: new subclass `OutputWriteError` in `errors.py`.**

Rationale:
- `<reason>` is `str(e)` from the caught `OSError`. This is a dynamic sub-message, the same pattern already used by `UnknownFunction` and `UndefinedVariable` (which carry `name`).
- Wrapping in a `CalcError` subclass keeps the error path uniform (raise → `error_message()` → print → exit 1) rather than introducing an inline format string in `__main__`.
- `error_message()` does not need a signature change; `description()` returns the full dynamic message.

```python
class OutputWriteError(CalcError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def description(self) -> str:
        return f"cannot write output: {self.reason}"
```

Usage in plot command:
```python
try:
    save_image(...)
except OSError as e:
    raise OutputWriteError(str(e)) from e
```

### 3.4 `error: unsupported format: <ext>; use .png or .svg`

**Recommendation: new subclass `UnsupportedFormat` in `errors.py`.**

Rationale:
- This is CLI validation (checked before any eval/render work). A dedicated class is more testable than an inline string.
- The `<ext>` component (e.g., `.bmp`) is dynamic.

```python
class UnsupportedFormat(CalcError):
    def __init__(self, ext: str) -> None:
        self.ext = ext
        super().__init__(ext)

    def description(self) -> str:
        return f"unsupported format: {self.ext}; use .png or .svg"
```

### 3.5 `error: expression undefined over entire domain`

**Recommendation: new subclass `DomainEmpty` in `errors.py`.**

Rationale:
- This is plot-specific but logically belongs with other domain/range errors.
- Unlike `DomainError` (raised per-sample during evaluation), `DomainEmpty` is raised after sampling is complete and all points were invalid.
- No dynamic component; simple fixed description.

```python
class DomainEmpty(CalcError):
    def description(self) -> str:
        return "expression undefined over entire domain"
```

### 3.6 `error: xmin must be less than xmax`

**Recommendation: new subclass `InvalidDomainBounds` in `errors.py`.**

Rationale:
- CLI argument validation; raised before evaluation begins.
- Fixed description, no dynamic component.

```python
class InvalidDomainBounds(CalcError):
    def description(self) -> str:
        return "xmin must be less than xmax"
```

---

## 4. `error_message()` Signature

**No change needed.** All new error classes follow the existing pattern: `description()` returns the full bare message (including any dynamic sub-message like `<reason>` or `<ext>`). The `error_message()` function prepends `error: ` as before.

---

## 5. File Placement

**Recommendation: add all new classes to the existing `src/calc/errors.py`.**

Rationale:
- The module is small (98 lines) and all errors are `CalcError` subclasses sharing the same base contract.
- A separate `src/calc/plot/errors.py` would add indirection without benefit at this scale.
- The plot command handler imports from `calc.errors` today; keeping everything there avoids a new import path.

If the plot module grows to have many dedicated errors in v0.6+ a split can be made then.

---

## 6. Summary Mapping

| Spec error string | Implementation path | Notes |
|---|---|---|
| `error: undefined function: <name>` | New `UndefinedFunction` class in `errors.py` | Avoids breaking `UnknownFunction` tests; format diverges |
| `error: undefined variable: <name>` | Existing `UndefinedVariable` (unchanged) | Exact match |
| `error: cannot write output: <reason>` | New `OutputWriteError(reason)` class in `errors.py` | Wraps OSError.reason |
| `error: unsupported format: <ext>; use .png or .svg` | New `UnsupportedFormat(ext)` class in `errors.py` | CLI validation |
| `error: expression undefined over entire domain` | New `DomainEmpty` class in `errors.py` | Post-sampling aggregate error |
| `error: xmin must be less than xmax` | New `InvalidDomainBounds` class in `errors.py` | CLI arg validation |

---

## 7. Flagged Breaking Change

`UnknownFunction.description()` currently returns `unknown function '{name}'`.
The spec mandates `undefined function: <name>` (different verb, separator, and quoting).
These **must not** be silently unified — existing tests covering `unknown function` will break.
The recommended resolution is a new `UndefinedFunction` class for the plot path; a follow-up issue should decide whether to consolidate the two classes and update `calc` subcommand tests.
