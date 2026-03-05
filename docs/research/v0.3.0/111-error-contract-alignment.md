# Research: Error Contract Alignment — UnknownName vs Spec, New ConstantReassignment

**Issue:** #111
**Date:** 2026-03-05
**Milestone:** v0.3.0

---

## Q1: Is UnknownName.description() safe to change?

**Answer: No, not without updating one test first.**

`tests/test_errors.py` line 70 hardcodes the current wording:

```python
def test_unknown_name_message():
    assert error_message(UnknownName("pi_approx")) == "error: unknown name 'pi_approx'"
```

This is the only location across the entire test suite that asserts the `"unknown name '...'"` string. No test in `test_evaluator.py` asserts the message text for `UnknownName`; it only checks that the correct exception type is *not* explicitly tested (UnknownName is not imported or raised-tested in test_evaluator.py at all).

**Audit summary:**

| File | Hardcoded UnknownName string? |
|------|-------------------------------|
| tests/test_errors.py:70 | YES — `"error: unknown name 'pi_approx'"` |
| tests/test_evaluator.py | NO — UnknownName not imported or string-checked |
| tests/test_cli.py | NO |
| tests/test_lexer.py | NO |
| tests/test_parser.py | NO |

**Conclusion:** The description change requires updating exactly one assertion in `test_errors.py`.

---

## Q2: Rename UnknownName → UndefinedVariable, or keep the class name?

**Recommendation: Rename to `UndefinedVariable`.**

Rationale:
- The v0.3 spec uses the concept "undefined variable" — matching the class name to the concept eliminates a mental translation layer.
- The impact is bounded and mechanical:
  - `src/calc/errors.py`: rename class definition.
  - `src/calc/evaluator.py`: update import (`UnknownName` → `UndefinedVariable`) and the one `raise UnknownName(...)` call.
  - `tests/test_errors.py`: update import line, update `test_unknown_name_message`, `test_unknown_name_stores_name`, and the class list in `test_new_subclasses_inherit_from_calc_error` (all trivially mechanical changes).
  - `tests/test_evaluator.py`: no changes needed (UnknownName is not imported there).

No other files reference `UnknownName`.

A keep-as-is approach (only change the description string) would leave a misleading class name ("unknown name" ≠ "undefined variable") and accumulate conceptual debt. The rename cost is low; skip it and it grows.

---

## Q3: ConstantReassignment design

**Pattern:** follows the same convention as `UnknownName` / `UnknownFunction` — a single `name: str` instance attribute, passed to `super().__init__`.

**Exact output format (spec):** `error: cannot reassign constant: pi` — no quotes around the name.

**Proposed class skeleton:**

```python
class ConstantReassignment(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"cannot reassign constant: {self.name}"
```

Note the absence of quotes in the f-string, consistent with the spec and unlike `UnknownFunction` which *does* quote its name. `ConstantReassignment` must be a distinct class (not reuse `UndefinedVariable`) because the error semantics differ — the name *is* defined; it just cannot be mutated.

---

## Q4: Responsibility boundary — where should the constant check live?

**Recommendation: evaluator layer for v0.3, with a clear migration note.**

Current state: `evaluator.py` owns `_DEFAULT_ENV = {"pi": ..., "e": ...}`. The evaluator is the only layer that knows which names are constants at runtime.

For v0.3, the likely design is:
- A new "statement runner" or thin interpreter receives assignment statements (`name = expr`).
- Before binding the result, it checks whether `name` is in a frozen constant set.
- If yes, it raises `ConstantReassignment(name)`.

At the time of v0.3 implementation there is no interpreter/statement-runner module. The check should therefore be placed in the **evaluator** initially, since that is where `_DEFAULT_ENV` lives and where `Name` lookup already happens. The constants set can be a module-level frozenset:

```python
_CONSTANTS: frozenset[str] = frozenset(_DEFAULT_ENV)
```

When a future statement-runner layer is introduced, the constant check migrates there. The `ConstantReassignment` import moves with it. This keeps the evaluator responsible only for *reading* the environment and leaves mutation policy to the caller — a clean separation that also makes the migration path obvious.

**Import implication:** For v0.3, `evaluator.py` imports `ConstantReassignment` from `calc.errors`. When a statement-runner is added, it takes over the import; `evaluator.py` drops it.

---

## Concrete Recommendations

1. **Rename `UnknownName` → `UndefinedVariable`** in `errors.py`, `evaluator.py`, and `tests/test_errors.py`. Update description to `f"undefined variable: {self.name}"` (no quotes).

2. **Add `ConstantReassignment`** to `errors.py` using the skeleton above.

3. **Place constant-guard logic in `evaluator.py`** for v0.3, using a `_CONSTANTS` frozenset derived from `_DEFAULT_ENV`. Raise `ConstantReassignment(name)` before any assignment mutates the env.

4. **Update `tests/test_errors.py`** — one string assertion and three symbol references; no structural test changes needed.
