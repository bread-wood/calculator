# Research: Evaluator env Safety — Mutable env per Invocation and Constant-Protection Mechanism

**Issue:** #114
**Date:** 2026-03-05
**Branch:** `114-research-evaluator-env-safety-mutable`

---

## Question 1 — Mutation of `_DEFAULT_ENV`

**Does `__main__.py` construct a fresh env per invocation today?**

No. `__main__.py` calls `evaluate(ast)` without passing an explicit `env`.
Inside `evaluate`, the guard is:

```python
if env is None:
    env = _DEFAULT_ENV
```

This assigns the *module-level singleton* directly to the local `env` parameter. Any write to `env` (e.g. `env["x"] = 1.0`) would mutate `_DEFAULT_ENV` globally. In the current v0.2 code, no writes to `env` ever occur (the evaluator only reads from it), so the bug is latent but not yet triggered.

**Do any existing tests mutate `_DEFAULT_ENV`?**

No. Every test that exercises `pi` or `e` does so via the `eval_expr()` helper, which calls `evaluate(ast)` with no explicit `env`. None of the tests write to `env` at all; the evaluator only performs `env[node.name]` reads. `_DEFAULT_ENV` is therefore **not mutated by any existing test**.

---

## Question 2 — Fresh env Strategy for v0.3

**Recommended pattern:**

```python
_DEFAULT_ENV: dict[str, float] = {"pi": math.pi, "e": math.e}

def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
    if env is None:
        env = dict(_DEFAULT_ENV)   # fresh copy; pi/e present, no aliasing
    ...
```

This is correct and sufficient. Each top-level call from `__main__.py` gets its own dict; variable assignments accumulate there and are discarded at end-of-call. The copy is O(2) — negligible cost.

**Impact on existing tests:**
None. Tests that check `pi` and `e` values go through `eval_expr()` → `evaluate(ast)`, which will receive the freshly-copied env. The constants have the same values as before. No test inspects the `env` object after evaluation. The change is transparent to the entire existing test suite.

---

## Question 3 — Constant-Protection Placement

**Where should `_CONSTANTS = frozenset({"pi", "e"})` live?**

**Recommendation: `evaluator.py` (module level), not the statement-runner layer.**

Rationale:

1. **Semantic ownership.** `_DEFAULT_ENV` already lives in `evaluator.py`. The constants are defined there; it is natural that the rule "these names are read-only" is enforced at the same layer that owns the namespace.

2. **No CLI coupling.** `_CONSTANTS` is purely a set of string names. It carries no CLI logic and imposes no dependency on any higher layer. Placing it in `evaluator.py` is no more coupled to the CLI than `_DEFAULT_ENV` already is.

3. **Enforcement site.** In v0.3, an `Assign` node handler will call into the evaluator (or a thin statement runner) to write `env[name] = value`. The constant-check must run before that write. If the check lives in `evaluator.py`, it is always enforced regardless of which caller drives evaluation. If it lived only in the statement-runner layer, a future caller that bypassed the statement runner could silently overwrite `pi`.

4. **Layering.** The stack is: `__main__` → statement runner → `evaluator`. Putting `_CONSTANTS` in `evaluator.py` keeps enforcement at the lowest layer that has visibility over the env, which is the correct defensive position.

Concrete placement:

```python
# evaluator.py
_CONSTANTS: frozenset[str] = frozenset({"pi", "e"})
```

The `Assign`-node handler (wherever it lives) calls:

```python
if name in _CONSTANTS:
    raise ConstantReassignment(name)
env[name] = value
```

If the handler is inside `evaluator.py` this import is free. If it is in a separate `runner.py`, it imports `_CONSTANTS` from `evaluator`.

---

## Question 4 — `_DEFAULT_ENV` Immutability Guarantee

**Should `_DEFAULT_ENV` become a `types.MappingProxyType`?**

**Recommendation: Yes, convert after adopting the fresh-copy strategy.**

```python
import types

_DEFAULT_ENV: types.MappingProxyType = types.MappingProxyType({"pi": math.pi, "e": math.e})
```

`dict(_DEFAULT_ENV)` still works — `dict()` accepts any mapping — so the copy idiom is unaffected.

**Impact on existing tests:**

No existing test writes to `_DEFAULT_ENV` directly (confirmed in Question 1). No test imports `_DEFAULT_ENV` for mutation. The only usage is the implicit `env = _DEFAULT_ENV` fallback inside `evaluate`, which is replaced by `env = dict(_DEFAULT_ENV)`. The `MappingProxyType` change therefore **breaks no existing test**.

The benefit is machine-enforced safety: a future accidental `_DEFAULT_ENV["x"] = 1` raises `TypeError` immediately rather than silently corrupting global state across calls. Given that v0.3 introduces statement-level mutation, this guard becomes important.

---

## Recommendations Summary

| Decision | Recommendation |
|---|---|
| env initialisation in `evaluate` | `env = dict(_DEFAULT_ENV)` when `env is None` |
| Caller (`__main__.py`) change needed? | No — the fix belongs entirely inside `evaluator.py` |
| `_CONSTANTS` placement | Module level in `evaluator.py` |
| `_DEFAULT_ENV` type | Convert to `types.MappingProxyType` |
| Any existing test broken? | None |

---

## Confirmation: `_DEFAULT_ENV` Not Currently Mutated

Searched all files under `tests/` for writes to `env` or `_DEFAULT_ENV`. No test passes a mutable env argument to `evaluate`, imports `_DEFAULT_ENV` for mutation, or triggers any code path that writes into `env`. The module-level dict is safe in v0.2 solely because the evaluator is read-only; in v0.3, the fresh-copy strategy must be in place before any assignment node is evaluated.
