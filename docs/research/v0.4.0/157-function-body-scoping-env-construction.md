# Research: Function Body Scoping — Constructing a Restricted Evaluation Environment at Call Time

**Issue:** #157
**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Decision reached

---

## Summary

When a user-defined function is called, the evaluator must evaluate the body in a
freshly-constructed environment that excludes the caller's variables. The recommended
approach is the **snapshot approach** for function visibility and **dict construction
from a constants dict** for env building.

---

## Q1 — Call-time env construction

**Decision:** Construct a fresh `dict` on every call.

At call time, build:

```python
body_env = dict(_CONSTANTS_VALUES)          # {"pi": math.pi, "e": math.e}
body_env[param_name] = evaluated_arg_value  # one entry per parameter
```

`_CONSTANTS_VALUES` is a new module-level plain `dict` (or use `dict(_DEFAULT_ENV)`)
holding only the two constants. The outer caller `env` is never passed into
`evaluate(body, body_env)`.

**Why a fresh dict?**
The body may contain assignments in future extensions, and isolating it guarantees
no leakage in either direction. The overhead of one `dict` allocation per call is
negligible for a calculator workload.

**Practical change to `evaluator.py`:**

- Add `_CONSTANTS_VALUES: dict[str, float] = {"pi": math.pi, "e": math.e}`.
- The existing `_CONSTANTS: frozenset` (used for reassignment checks) stays unchanged.
- `_DEFAULT_ENV` (used for top-level expression evaluation) also stays unchanged.

---

## Q2 — User-defined function visibility inside a body: snapshot vs full-store

**Decision: Snapshot approach.**

`UserFunction` captures `available_fns: dict[str, UserFunction]` at definition time.

```python
@dataclass(frozen=True)
class UserFunction:
    name: str
    param: str                                # single parameter for v0.4.0
    body: ASTNode
    available_fns: dict[str, "UserFunction"]  # snapshot at def time
```

**Rationale:**

| Criterion | Snapshot | Full-store |
|-----------|----------|------------|
| Correctness without extra invariants | Yes — self-contained | Relies on store never being mutated after definition |
| Future persistence / serialisation | Straightforward | Requires reconstructing ordering |
| Memory cost | One extra dict per function (tiny for calculator scale) | None |
| Implementation complexity | Slightly higher at def time | Slightly higher at call time (thread store everywhere) |
| Forward-reference safety | Guaranteed structurally | Must be enforced separately |

The snapshot approach makes the function object self-describing. Passing the full
store into every `evaluate` call would require adding a new parameter to a function
that currently takes only `node` and `env`, increasing coupling. The snapshot
naturally enforces the "only functions defined before me" rule without any
ordering check at call time.

**Procedure at call time (incorporating Q1):**

```python
def _call_user_fn(fn: UserFunction, arg_value: float) -> float:
    body_env: dict[str, float] = dict(_CONSTANTS_VALUES)
    body_env[fn.param] = arg_value
    return evaluate(fn.body, body_env, fn.available_fns)
```

`evaluate` gains a third parameter `user_fns: dict[str, UserFunction] | None = None`
used only when resolving `Call` nodes that are not in `_FUNCTION_TABLE`.

---

## Q3 — Infinite-loop / recursion prevention

**Decision:** Validation at **definition time** by walking the body AST.

When `def f(x) = <body>` is executed:

1. Walk every `Call` node in `<body>`.
2. For each called name, check it exists in the *current* `available_fns` snapshot
   (which does **not** yet include `f` itself).
3. If any call target is missing → raise `UnknownFunction`.

This is the natural consequence of taking a snapshot at definition time: `f` is not
yet in the store when the snapshot is taken, so any self-call in the body is
immediately rejected. Mutual recursion is blocked for the same structural reason —
`g` cannot yet reference `f` if `f` is defined after `g`, and vice-versa.

No runtime cycle detection is needed.

---

## Q4 — Constants in function scope

**Decision:** Add `_CONSTANTS_VALUES: dict[str, float]` alongside the existing
`_CONSTANTS: frozenset`.

```python
_CONSTANTS_VALUES: dict[str, float] = {"pi": math.pi, "e": math.e}
_CONSTANTS: frozenset[str] = frozenset(_CONSTANTS_VALUES)  # replaces literal set
```

This avoids duplicating the actual float values. Both the top-level `_DEFAULT_ENV`
and the per-call body env are derived from `_CONSTANTS_VALUES`. `_DEFAULT_ENV` can
be redefined as `MappingProxyType(_CONSTANTS_VALUES)` with no behaviour change.

---

## Implementation checklist for the evaluator PR

- [ ] Add `_CONSTANTS_VALUES: dict[str, float]` and derive `_CONSTANTS` from it.
- [ ] Define `UserFunction` dataclass with `name`, `param`, `body`, `available_fns`.
- [ ] In `execute_statement`, handle a new `FunctionDef` AST node:
  - Walk body AST; reject unknown calls → `UnknownFunction`.
  - Snapshot `available_fns` from current function store.
  - Store `UserFunction` in a separate `fn_store: dict[str, UserFunction]`.
- [ ] Extend `evaluate` signature to accept `user_fns: dict[str, UserFunction] | None`.
- [ ] In the `Call` branch: try `_FUNCTION_TABLE` first, then `user_fns`; build
  `body_env` from `_CONSTANTS_VALUES` + param; recurse with that env and
  `fn.available_fns`.
- [ ] `execute_statement` threads `fn_store` into `evaluate` calls.
