# Research: Error Class Design for Function Errors — New Classes vs Modify Existing

**Issue:** #155
**Date:** 2026-03-05
**Milestone:** v0.4.0

---

## Summary

The v0.4.0 spec introduces four new error conditions for user-defined functions.
Two conditions map to existing error classes (`UnknownFunction`, `WrongArity`) with
different message wording. Two are genuinely new (`FunctionAlreadyDefined`,
`CannotRedefineBuiltin`). This document resolves the design questions before
`errors.py` work begins.

---

## Current State Audit

### Existing classes and messages

| Class | Current `description()` | v0.4 spec required stderr |
|-------|--------------------------|--------------------------|
| `UnknownFunction(name)` | `unknown function '{name}'` | `undefined function: {name}` |
| `WrongArity(name, n)` | `'{name}' expects {n} argument[s]` | `wrong number of arguments: {name} expects {n}` |

Both classes are used by the evaluator today for **built-in** function dispatch
(lines 84 and 87 of `evaluator.py`). The test suite pins the current wording in
`tests/test_errors.py` lines 59, 63, and 67.

### New conditions (no existing class)

| Condition | Required stderr |
|-----------|----------------|
| Duplicate function definition | `error: function already defined: f` |
| Shadow a built-in with user def | `error: cannot redefine built-in: f` |

---

## Q1: Modify vs Add for UnknownFunction and WrongArity

### Option A — Modify existing classes (change `description()` strings)

- One code change per class; `__main__` and evaluator stay unchanged.
- **Breaking**: tests `test_unknown_function_message`, `test_wrong_arity_singular`,
  `test_wrong_arity_plural` all fail and must be updated.
- **Semantic shift**: the wording for built-in misses changes too (e.g. calling
  `sqrt(1,2)` emits `wrong number of arguments: sqrt expects 1` instead of
  `'sqrt' expects 1 argument`). The v0.1.x–v0.3.x success criteria do not pin
  these exact strings, so regression risk is low internally. Any external CLI
  consumers parsing the old wording would break.

### Option B — Add subclasses / sibling classes

- `UnknownFunction` keeps its message for built-in misses.
- New `UndefinedFunction` (or `UndefinedUserFunction`) class emits the v0.4 wording.
- Two parallel raise-sites in `__main__` / interpreter: one per context.
- Test suite for existing classes needs no changes.

### Option C — Modify existing classes and update tests (recommended)

The distinction between "unknown built-in" and "undefined user-defined function"
is artificial at the user-facing level. From the user's perspective, calling
`f(1)` when `f` does not exist should produce the same message regardless of
whether `f` was defined by the user or expected to be a built-in. The v0.4 spec
already mandates unified wording with "undefined function". Maintaining two
separate classes to preserve old wording adds complexity with no user benefit.

**Recommendation: Modify the existing classes and update affected tests.**

Rationale:
- The old wording (`unknown function 'f'`, `'f' expects N argument[s]`) is
  inconsistent with the rest of the error vocabulary (compare `undefined variable: x`,
  `cannot reassign constant: pi`). The v0.4 spec corrects this.
- There are only three test assertions to update — a low mechanical cost.
- Keeping one class per concept (rather than a parallel hierarchy) keeps
  `__main__` and the interpreter simple.
- The v0.1.x–v0.3.x milestones did not publish a stable error-message contract;
  no external consumers are expected.

---

## Q2: Separation of Built-in vs User-Defined Errors

Given the recommendation above (Option C — modify existing classes), both built-in
and user-defined function lookup failures raise `UnknownFunction`, and both
arity mismatches raise `WrongArity`. This is the simplest approach.

If future tests need to distinguish the two call sites, a `source` attribute
(`"builtin"` vs `"user"`) can be added to the exception later without changing
the public message. For v0.4.0, a single class per concept suffices.

---

## Q3: New Error Classes for FunctionAlreadyDefined and CannotRedefineBuiltin

These are genuinely new classes. They follow the same pattern as
`UndefinedVariable` and `ConstantReassignment`: one `name: str` argument,
stored on `self`, passed to `super().__init__`, and reflected in `description()`.

### Proposed skeletons

```python
class FunctionAlreadyDefined(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"function already defined: {self.name}"


class CannotRedefineBuiltin(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot redefine built-in: {self.name}"
```

Notes:
- No quotes around `{self.name}`, consistent with `UndefinedVariable` and
  `ConstantReassignment` (and with the spec).
- `CannotRedefineBuiltin` is **not** a subclass of `FunctionAlreadyDefined`; the
  semantics differ (one is a duplicate user def, the other is an attempt to shadow
  a built-in). Keeping them as siblings makes assertion on exception type
  unambiguous in tests.
- Where these are raised (interpreter / statement runner, not the evaluator) is an
  implementation decision for the implementing issue, not this research.

---

## Q4: Arg-Count Message Format and Pluralisation

The spec mandates: `wrong number of arguments: f expects 1`

There is no plural form in the spec table. However, the spec shows only the
singular example. Two sub-options:

**Option 4a — Drop pluralisation entirely:**
```python
def description(self) -> str:
    return f"wrong number of arguments: {self.name} expects {self.expected}"
```
Simple; matches the spec example exactly; avoids any pluralisation edge case.

**Option 4b — Keep pluralisation with new prefix:**
```python
def description(self) -> str:
    noun = "argument" if self.expected == 1 else "arguments"
    return f"wrong number of arguments: {self.name} expects {self.expected} {noun}"
```
More informative for functions expecting 2+ arguments (e.g. `pow`, `atan2`);
consistent with English grammar.

**Recommendation: Option 4b (keep pluralisation, update prefix).**

The spec table is illustrative, not exhaustive. Emitting `pow expects 2 arguments`
is clearer than `pow expects 2`. The additional word does not conflict with the
spec's required prefix `wrong number of arguments: f expects`. Existing test cases
`test_wrong_arity_singular` and `test_wrong_arity_plural` become straightforward
updates to the new prefix and suffix.

---

## Concrete Recommendations

### Classes to modify

| Class | Change |
|-------|--------|
| `UnknownFunction` | Change `description()` to `f"undefined function: {self.name}"` (drop quotes, change prefix) |
| `WrongArity` | Change `description()` to `f"wrong number of arguments: {self.name} expects {self.expected} {noun}"` (new prefix, drop quotes around name) |

### Classes to add

| Class | `description()` output |
|-------|------------------------|
| `FunctionAlreadyDefined(name)` | `function already defined: {name}` |
| `CannotRedefineBuiltin(name)` | `cannot redefine built-in: {name}` |

### Tests to update (tests/test_errors.py)

| Test | Required change |
|------|----------------|
| `test_unknown_function_message` (line 59) | Update expected string from `"error: unknown function 'sqrt'"` to `"error: undefined function: sqrt"` |
| `test_wrong_arity_singular` (line 63) | Update from `"error: 'abs' expects 1 argument"` to `"error: wrong number of arguments: abs expects 1 argument"` |
| `test_wrong_arity_plural` (line 67) | Update from `"error: 'pow' expects 2 arguments"` to `"error: wrong number of arguments: pow expects 2 arguments"` |
| *(new)* `test_function_already_defined_message` | Assert `error_message(FunctionAlreadyDefined("f")) == "error: function already defined: f"` |
| *(new)* `test_cannot_redefine_builtin_message` | Assert `error_message(CannotRedefineBuiltin("sqrt")) == "error: cannot redefine built-in: sqrt"` |

### No changes required in

- `src/calc/evaluator.py` — existing `UnknownFunction` and `WrongArity` raise-sites remain correct; messages update automatically.
- Any other source file — the two new classes will be raised by the function-definition layer (to be implemented separately).

---

## Decision Summary

1. **Modify vs add:** Modify `UnknownFunction` and `WrongArity` in place. Do not add parallel classes. Update the three affected test assertions.

2. **Separation:** One class per concept. Built-in and user-defined function errors share the same class; context differences can be added as attributes later if needed.

3. **New classes:** Add `FunctionAlreadyDefined` and `CannotRedefineBuiltin` following the `UndefinedVariable`/`ConstantReassignment` pattern (single `name` arg, no quotes in message).

4. **Pluralisation:** Keep pluralisation in `WrongArity`; change the prefix to `wrong number of arguments:` and remove the surrounding quotes from the function name.
