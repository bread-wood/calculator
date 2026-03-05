# Research: User-Function AST Serialization Strategy for Future REPL Persistence

**Issue:** #156
**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Complete

---

## Context

The v0.4.0 spec requires:

> "The function definition and call mechanism must extend to a persistent REPL
> environment in a future version — specifically, function definitions must be
> representable as serializable values without redesigning the runtime."

A `UserFunction` will be represented at minimum as `(params: list[str], body: ASTNode)`.
The body is an AST tree composed of dataclass instances (`Number`, `BinaryOp`, `UnaryOp`,
`Name`, `Call`). The serialization strategy chosen for the body shapes both the
`FunctionDef` AST node and the `UserFunction` evaluator type.

The current `FunctionEntry` design (storing `fn: Callable[..., float]`) is explicitly
**not** the pattern user functions should follow — lambdas/callables are not serializable.

---

## Q1 — Source-string approach

**Question:** Store only the raw source expression string as `body_src: str`; re-parse
on load. Does this satisfy "without redesigning the runtime"?

**Finding:**

Storing the source string is the simplest approach: a `UserFunction` becomes
`(params: list[str], body_src: str)`, which serializes trivially to JSON. However,
it has two significant liabilities:

1. **Re-parsing requirement.** Loading a persisted function requires invoking the
   parser, meaning the parser must be available in any environment that reads the
   store. This is true today but couples persistence to the parser lifecycle.

2. **Grammar fragility.** If the expression grammar changes (new operators, changed
   precedence, renamed token types), previously-stored source strings may parse
   differently or fail entirely. The stored string is valid only relative to the
   parser version that produced it.

3. **Representation asymmetry.** The evaluator operates on AST nodes, not strings.
   The `execute_statement` / `evaluate` pipeline expects `ASTNode`. Storing a string
   means the `UserFunction` must re-parse before every call (or cache the result,
   re-introducing the AST internally). Either way, the AST is the real working
   representation.

4. **"Without redesigning the runtime" test.** Loading a source string does not
   redesign the runtime — the parser already exists. But re-parsing on every function
   call would be a runtime performance concern; caching the parsed AST inside
   `UserFunction` recreates the AST-as-body model anyway. The source-string approach
   does not actually avoid storing AST state; it merely defers it.

**Verdict:** Source-string is viable as a secondary, human-readable field but should
not be the *sole* body representation. Relying on it as the canonical form introduces
grammar-fragility and hides a parse-on-call performance issue.

---

## Q2 — AST-as-JSON approach

**Question:** Serialize AST nodes as JSON (`{"type": "BinaryOp", "op": "+", "left":
..., "right": ...}`). Does this couple the persistence format too tightly to the
internal AST shape?

**Finding:**

The existing AST node types (`Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call`) are
simple dataclasses with no methods, no circular references, and field types that
are either primitives (`float`, `str`) or other AST nodes. This is an ideal shape
for structural JSON serialization.

Pros:
- Round-trips cleanly without the parser.
- Survives grammar changes that do not affect AST structure (e.g., adding a new
  token type that desugars to existing nodes).
- Decouples the evaluator from the parser at load time.
- The AST is already the canonical runtime representation — serializing it directly
  avoids a parse-on-load step.
- `to_dict` / `from_dict` methods (or a small dispatch table) on the five existing
  node types add ~30 lines of code and introduce no new dependencies.
- Libraries like `cattrs` or `dataclasses-json` could automate this further, but
  the AST is simple enough that a hand-written converter is preferable to an
  additional dependency.

Cons:
- Couples the persistence format to AST node names and field names. A rename of
  `BinaryOp` → `InfixOp` in a future refactor would require a migration.
- Slightly more implementation than the source-string approach.

**Verdict:** AST-as-JSON is the correct canonical serialization format. The AST
dataclasses are already the right shape. The coupling risk is low because the five
expression node types are stable and unlikely to be renamed without a deliberate
versioning decision. A `"format_version": 1` envelope in the JSON store is sufficient
to gate future migrations.

---

## Q3 — Pickle

**Finding:** Rejected. Pickle is fragile across Python versions and class renames,
produces opaque binary blobs, and offers no migration path. Not suitable for a
persistent store intended to survive upgrades.

---

## Q4 — FunctionDef AST node design

**Question:** Should `FunctionDef` store `body: ASTNode` or `body_src: str` or both?

**Finding:**

The evaluator operates on `ASTNode`. The parser's job is to produce `ASTNode`.
There is no runtime reason to retain `body_src` inside `FunctionDef` — the source
text is consumed during parsing and discarded. Storing `body_src` inside the AST
node would be a form of "unparsed residue" that no other node carries and that
would be misleading (the source string is not kept for `Assignment.value`, for
example).

The recommended `FunctionDef` shape for `parser.py`:

```python
@dataclass
class FunctionDef:
    name: str
    params: list[str]
    body: ASTNode
```

This mirrors the existing `Assignment` pattern (`name: str`, `value: ASTNode`). The
`body` field is the parsed expression tree. No source string is stored in the node.

The corresponding `Statement` union expands to:

```python
Statement = Assignment | FunctionDef | ASTNode
```

`FunctionDef` is statement-level only (cannot appear as a sub-expression), consistent
with the `Assignment` precedent from issue #113.

---

## Q5 — Scope of the serialization constraint in v0.4.0

**Question:** Does "representable as serializable values" require shipping serialization
code in v0.4.0, or only a serialization-friendly data model?

**Finding:**

The spec constraint is forward-looking: it says function definitions must be
*representable* as serializable values, not that serialization must be *implemented*
in v0.4.0. The REPL and persistence layer are explicitly non-goals for this version.

The constraint translates to two concrete v0.4.0 requirements:

1. **`UserFunction` must not store a `Callable`.** The current `FunctionEntry.fn:
   Callable[..., float]` pattern is explicitly forbidden for user functions because
   callables are not serializable. `UserFunction` must store `params` and `body`
   (the AST), not a compiled callable.

2. **The AST node types used in `body` must be serializable by construction.**
   Because they are simple dataclasses with primitive and nested-node fields, this
   is already true without any code changes.

No `to_dict` / `from_dict` methods, no JSON encoder, and no persistence store need
to ship in v0.4.0. The data model alone satisfies the constraint.

---

## Decision

**Canonical serialization strategy: AST-as-JSON.**

The `body` field of `FunctionDef` and `UserFunction` stores an `ASTNode` (parsed
form). If/when REPL persistence is implemented, AST nodes will be serialized as
typed JSON dicts. Source strings are not stored in either the AST node or the
runtime type.

---

## Recommended data model

### `parser.py` additions

```python
@dataclass
class FunctionDef:
    name: str
    params: list[str]
    body: ASTNode          # parsed expression tree; no source string stored

Statement = Assignment | FunctionDef | ASTNode
```

### `evaluator.py` additions

```python
@dataclass(frozen=True)
class UserFunction:
    params: list[str]
    body: ASTNode          # NOT a Callable — serialization-friendly by design
```

`UserFunction` is looked up in a separate user-function table alongside
`_FUNCTION_TABLE`. When called, `evaluate(body, child_env)` is invoked with a
child environment that maps parameter names to argument values, consistent with the
scope-chain model from issue #109.

---

## What ships in v0.4.0 vs future versions

| Concern | v0.4.0 | Future REPL version |
|---|---|---|
| `FunctionDef` AST node | Yes | — |
| `UserFunction(params, body: ASTNode)` | Yes | — |
| AST `to_dict` / `from_dict` | No | Yes |
| JSON persistence store | No | Yes |
| Source-string field in `UserFunction` | No | Optional (human-readable aid) |

---

## Interaction with prior research

- **Issue #109 (scope model):** `UserFunction` is evaluated by building a child env
  `{param: arg_value, ...}` and calling `evaluate(body, child_env)`. The flat-dict
  scope model from v0.3 is directly compatible; no scope redesign is needed.
- **Issue #113 (AST data model):** `FunctionDef` follows the same dataclass pattern
  as `Assignment`. The `Statement` union extends cleanly.
- **Issue #110 (parser ambiguity):** `FunctionDef` introduces new syntax
  (`def name(params) = expr`) that is unambiguous with assignment and expression
  statements at the statement-level parse point; no grammar conflict arises.
