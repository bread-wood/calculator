# Research: Scope Model Extensibility — Flat Dict Env vs Scope Chain for v0.4 Function Parameters

**Issue:** #109
**Date:** 2026-03-05
**Status:** Finding

---

## Context

The v0.3 evaluator uses a single `dict[str, float]` as its variable namespace (`env`).
Constants `pi` and `e` live in `_DEFAULT_ENV`. The evaluator signature is:

```python
def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
```

The key unknown: can this flat dict extend cleanly to v0.4 function parameter scoping,
or does adding user-defined functions require replacing the scope model?

---

## Question 1 — Extension path

**Can a scope chain be retrofitted onto v0.3's flat env without breaking the v0.3 calling convention?**

Yes. The minimum change is to introduce a thin `Scope` type that wraps a stack of dicts
but exposes the same read/write interface that v0.3's single-dict `env` currently provides:

```python
class Scope:
    def __init__(self, frames: list[dict[str, float]] | None = None):
        self._frames = frames or [{}]

    def get(self, name: str) -> float | None:
        for frame in reversed(self._frames):
            if name in frame:
                return frame[name]
        return None

    def set(self, name: str, value: float) -> None:
        self._frames[-1][name] = value

    def push(self) -> "Scope":
        return Scope(self._frames + [{}])
```

At the v0.3 call site, callers that pass a plain `dict[str, float]` can be wrapped once:

```python
if isinstance(env, dict):
    env = Scope([env])
```

This is a single-line shim; all v0.3 tests continue to pass unmodified. The only change
to `evaluate`'s internal logic is replacing `env[name]` / `env[name] = value` with
`env.get(name)` / `env.set(name, value)`.

**Minimum change:** introduce `Scope`, add a `dict`→`Scope` shim at the entry point,
update `Name` and assignment handling inside `evaluate`. No structural refactor needed.

---

## Question 2 — Shadowing semantics

**Does stack-of-dicts lookup cover the spec's shadowing requirement, or does v0.4 need write-isolation?**

Stack-of-dicts with inner-first lookup covers the read side of shadowing: a parameter
named `x` shadows an outer `x` when the evaluator resolves a `Name` node.

Write-isolation is also required. When the function body executes `x = ...`, that
assignment must land in the innermost frame, not in the caller's frame. The `Scope.set`
implementation above always writes to `self._frames[-1]`, which is the frame pushed for
the function call. Callers never see that write because they hold a reference to the
outer `Scope` (or the original dict), not to the child `Scope` returned by `push()`.

Concretely, for a v0.4 call like:

```
f(x) = x * 2; y = 3; f(y + 1)
```

Evaluation of the function body uses `scope.push()`, which creates a new innermost
frame. Any assignment inside the body is invisible to the caller's scope.

**Conclusion:** stack-of-dicts with `set` targeting the innermost frame provides both
shadowing and write-isolation. No additional mechanism is needed.

---

## Question 3 — Constants layer

**Should `pi` and `e` be a read-only sentinel layer at the bottom of the scope chain, or checked separately?**

Currently `pi` and `e` live in `_DEFAULT_ENV` (a module-level dict that doubles as the
default `env`). This is a design coupling: the same dict that holds constants also
holds user-assigned variables, which is why constant-reassignment must be detected
explicitly in the evaluator rather than enforced by the data structure.

**Recommendation:** make constants a dedicated read-only base frame at the bottom of
the scope chain. A `FrozenFrame` (or simply a `frozenset` of protected names) ensures
that `set` raises `ConstantReassignment` before the write reaches the dict.

```python
_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}

def make_default_scope() -> Scope:
    return Scope(frames=[_CONSTANTS], readonly_base=True)
```

Alternatively (simpler for v0.3): keep the current `_CONSTANTS` check in the evaluator
and leave `_DEFAULT_ENV` as a plain dict. The key requirement is that v0.3 must **not
mutate `_DEFAULT_ENV`** when assigning user variables — it must copy or shadow it.
A scope chain naturally prevents this because user assignments go into a fresh top frame,
never into the base constants frame.

**Recommendation for v0.3:** do not mutate `_DEFAULT_ENV` directly; pass a fresh user
frame on top of constants. This is the one design choice (see Q4 / Decision boundary below)
that prevents v0.4 replacement.

---

## Question 4 — Evaluator signature

**Should `evaluate(node, env)` change to `evaluate(node, env: Scope)`, or can `env` stay a plain dict?**

The signature `evaluate(node: ASTNode, env: dict[str, float] | None = None)` can be
preserved in v0.3 without any public-API breakage if `Scope` is introduced as an
internal type with a `dict`-compatible shim. External callers (tests, `__main__`) that
pass a plain dict continue to work.

For v0.4, the signature should evolve to `evaluate(node, env: Scope)` so that
the evaluator can call `env.push()` when entering a function body. This is a
**non-breaking extension** if done as an overload:

```python
def evaluate(node: ASTNode, env: dict[str, float] | Scope | None = None) -> float:
    if env is None:
        env = make_default_scope()
    elif isinstance(env, dict):
        env = Scope([env])
    ...
```

No v0.3 test needs updating. v0.4 can pass a `Scope` directly and call `env.push()`
inside function-call dispatch.

---

## Decision Boundary

The one v0.3 design choice that would **force replacement** rather than extension in v0.4:

> **Mutating `_DEFAULT_ENV` in-place** (i.e. treating the module-level dict as both
> the constants store and the mutable user-variable store).

If `evaluate` writes user variables directly into `_DEFAULT_ENV`, then:
- Constants are no longer protected across calls (state leaks between invocations).
- Introducing a scope chain in v0.4 requires finding and fixing every write site.
- The flat dict becomes load-bearing state that callers can't safely replace.

---

## Recommendation

**(A) v0.3 flat dict is the foundation — with one constraint.**

The v0.3 flat dict `env` is an acceptable foundation for v0.4, provided that:

1. **User variables are never written into `_DEFAULT_ENV`.**
   The evaluator must initialise a fresh mutable dict (or `Scope` frame) per invocation
   and look up constants from `_DEFAULT_ENV` separately (or as a read-only base frame).

2. **`evaluate`'s env parameter is typed as `dict[str, float] | Scope`** (or just
   `dict[str, float]` with a v0.3-internal copy-on-write convention). This keeps the
   public signature stable for v0.4 to widen without a rename.

3. **Constant protection stays in the evaluator** (as it is now), not buried in
   mutation side-effects of the dict.

Meeting constraint (1) means v0.4 can add `Scope` as a thin wrapper, call
`env.push()` at function-call dispatch, and everything else stays the same.
The changeset is additive: one new class, one shim, updated `Name`/assignment dispatch.

If v0.3 violates constraint (1) — writes user vars into the shared `_DEFAULT_ENV` —
the scope model becomes a stepping stone and v0.4 must replace it.

---

## Summary Table

| Question | Answer |
|---|---|
| Extension path | Stack-of-dicts `Scope` wraps the flat dict; one-line shim preserves v0.3 API |
| Shadowing semantics | Inner-first lookup + write-to-innermost-frame covers both shadowing and write-isolation |
| Constants layer | Keep constants in a separate read-only base; never mutate `_DEFAULT_ENV` with user vars |
| Evaluator signature | Signature can stay `dict \| Scope` with an `isinstance` shim; evolves to `Scope`-only in v0.4 |
