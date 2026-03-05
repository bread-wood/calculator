# Research: AST data model — Assignment and Program node design

**Issue:** #113
**Milestone:** v0.3.0
**Date:** 2026-03-05
**Status:** Complete

---

## Context

The v0.3 grammar introduces assignment and a multi-statement program:

```
program   = statement { ';' statement }
statement = IDENT '=' expression   # Assignment
          | expression
```

The existing AST node types (`Number`, `BinaryOp`, `UnaryOp`, `Name`, `Call`) live in `src/calc/parser.py`. The `ASTNode` type alias is:

```python
ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

---

## Q1 — Assignment node shape

**Question:** Should `Assignment` carry a position/span, or is that out of scope for v0.3?

**Finding:**

The minimal v0.3 shape is:

```python
@dataclass
class Assignment:
    name: str
    value: ASTNode
```

No other node type currently carries position information. The lexer (`Lexer`) does not expose token offsets in the public API; adding span tracking to `Assignment` alone would be inconsistent and would not benefit error messages unless all nodes gain the same information. Retrofitting spans uniformly is a separate concern that cuts across the whole codebase.

**Recommendation:** Omit position/span from `Assignment` in v0.3. Add only `name: str` and `value: ASTNode`. Span tracking should be addressed in a dedicated cross-cutting issue if it becomes necessary.

---

## Q2 — Program / StatementList wrapper

**Question:** Should `parse()` return a `Program(statements: list[Statement])` wrapper node, or a plain `list[Statement]`?

**Finding:**

The current `parse()` return type is `ASTNode` (a single expression node). Changing it to `list[Statement]` is a breaking change to the public interface.

A `Program` wrapper preserves the invariant that `parse()` always returns a single structured value, makes the tree uniformly traversable (an evaluator/interpreter loop only ever receives one object), and avoids a special case for "the top level is a list, everything else is a node."

A plain `list` is simpler but:
- Callers (e.g., `__main__.py`, tests) must check `isinstance(result, list)` before iterating.
- It makes the AST type heterogeneous at the top level.
- v0.4 will likely need a `Program` node anyway (for user-defined function bodies that are also statement lists).

**Recommendation:** Introduce a `Program` wrapper node:

```python
@dataclass
class Program:
    body: list[Statement]
```

Change `parse()` to `-> Program`. Update `__main__.py` to iterate `result.body`. This keeps the tree uniform and makes the v0.4 transition easier.

---

## Q3 — ASTNode union update

**Question:** Add `Assignment` to `ASTNode`, or introduce a separate `Statement = Assignment | ASTNode` union?

**Finding:**

`Assignment` is only valid at statement level; it cannot appear as a sub-expression. Admitting it into `ASTNode` would allow the type system to represent `BinaryOp(left=Assignment(...), right=...)`, which is semantically impossible. This creates dead states in the type union.

The existing codebase already has a natural split: the parser's top-level entry point produces "statement-level" nodes, while everything else is "expression-level." Naming this split makes the code self-documenting.

The overhead is one additional type alias:

```python
Statement = Assignment | ASTNode   # statement-level union
```

`ASTNode` remains unchanged as the expression-level union. `Program.body` is typed `list[Statement]`. The evaluator dispatches on `Statement` at the top level.

**Recommendation:** Keep `ASTNode` as the expression-level union. Add:

```python
Statement = Assignment | ASTNode
```

`Assignment` is **not** added to `ASTNode`. `Program.body: list[Statement]`. This is precise, self-documenting, and eliminates impossible states.

---

## Q4 — Evaluator impact and v0.4 scope model

**Question:** Should `evaluate()` handle `Assignment`, or should a separate `execute_statement()` be introduced? How does this interact with the v0.4 scope model (issue #109)?

**Finding:**

Issue #109 concludes that the v0.3 flat `dict[str, float]` env is the foundation and must expose a stable interface that v0.4 can extend without replacement. The key constraint is that v0.4 function parameters must shadow outer variables, which a scope chain (`list[dict]` or a `Scope` object) handles cleanly.

If `Assignment` is handled inside `evaluate()`:
- `evaluate()` must return a sentinel or mutate `env`, breaking the current pure-function signature `(node, env) -> float`.
- A single function cannot have two return types (`float` for expressions, `None`/`float` for assignments).
- This conflates evaluation (compute a value) with execution (mutate state), making it harder to introduce a read-only scope for function bodies in v0.4.

A separate `execute_statement(stmt: Statement, env: dict[str, float]) -> float | None` function:
- Keeps `evaluate()` a pure `(ASTNode, env) -> float` function.
- Handles `Assignment` by writing to `env` and returning the assigned value (or `None`).
- For expression statements, delegates to `evaluate()`.
- The evaluator loop in `__main__.py` calls `execute_statement()` per statement in `program.body`.

When v0.4 adds user-defined functions, `execute_statement()` can accept a `Scope` instead of a raw dict, or the caller can construct a child scope before passing it in. `evaluate()` itself never changes signature.

**Recommendation:** Introduce `execute_statement(stmt: Statement, env: dict[str, float]) -> float | None` in `evaluator.py`. Do **not** add `Assignment` handling inside `evaluate()`. This preserves `evaluate()` as a pure expression evaluator and aligns directly with the v0.4 scope-extension path identified in issue #109.

---

## Recommended node design (summary)

```python
# parser.py additions

@dataclass
class Assignment:
    name: str
    value: ASTNode          # rhs is an expression — no spans in v0.3

@dataclass
class Program:
    body: list[Statement]

Statement = Assignment | ASTNode   # new type alias; ASTNode is unchanged

# parse() return type changes: ASTNode  ->  Program
```

```python
# evaluator.py additions

def execute_statement(stmt: Statement, env: dict[str, float]) -> float | None:
    if isinstance(stmt, Assignment):
        val = evaluate(stmt.value, env)
        env[stmt.name] = val
        return val
    return evaluate(stmt, env)   # expression statement
```

`evaluate()` signature is unchanged. `__main__.py` iterates `program.body`, calling `execute_statement()` for each statement.

---

## Interaction with scope-model research (issue #109)

Issue #109 recommends keeping v0.3's flat `dict[str, float]` as the canonical env, but specifies that the interface must allow a `Scope` abstraction to be dropped in for v0.4. The design above is compatible:

- `execute_statement(stmt, env)` takes `env` as an explicit argument. In v0.4 the caller can pass a child scope (a new `dict` pre-populated with function parameters) without changing the function's signature.
- `evaluate(node, env)` never writes to `env`, so it works identically inside a function body scope.
- The `Statement` / `ASTNode` split means the type checker enforces that `Assignment` cannot appear inside an expression, ruling out accidental assignment-as-expression bugs in user-defined function bodies.

No v0.3 interface choice in this design forces a breaking change in v0.4.
