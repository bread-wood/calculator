# Research: Constants and Future-Variable Symbol Table Interface

**Issue:** #56
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Recommendation

---

## Context

The v0.2.0 spec requires:

> The constant and function namespaces must remain extensible to user-defined variables (`x = 5`) in a future version without a parser rewrite.

This research designs the symbol table interface so that `pi` and `e` in v0.2.0 use the same evaluation path that a future user variable `x` will use — with no parser changes required when variables arrive.

Prior research establishing foundations:
- **#38** confirms the v0.1.x parser extends cleanly via additive changes (new `IDENT` token, new `Identifier` / `FunctionCall` AST nodes, one-token look-ahead in `_parse_primary`).
- **#39** specifies the `FunctionEntry` struct and `FUNCTION_TABLE` design.
- **#43** recommends a unified symbol table with a `readonly` flag and a separate function dispatch table.

This document resolves the four open interface questions and specifies the `evaluate()` signature for v0.2.0.

---

## Q1 — AST Node Type: `Name` node or parse-time `Number` resolution?

**Decision: emit a `Name(id: str)` AST node; resolve at evaluation time via dict lookup.**

### Options considered

| Approach | Description | Verdict |
|----------|-------------|---------|
| **A — `Name` node, eval-time lookup** | Parser emits `Name("pi")`; evaluator does `env["pi"]` | ✓ Recommended |
| **B — Parse-time constant folding** | Parser imports `CONSTANTS`, replaces `pi` with `Number(3.14…)` | ✗ Rejected |

### Rationale for A

**Parser coupling.** Option B requires the parser to import the constants table. That couples two layers that the current architecture keeps cleanly separate. When user-defined variables arrive, the parser still cannot know the value of `x` at parse time (it depends on earlier assignments in the same session), so the parse-time fold would need to be removed — a parser change the spec explicitly wants to avoid.

**Uniformity.** A future user variable `x` will produce exactly `Name("x")` from the parser. By designing `pi` to produce `Name("pi")` today, the evaluator's lookup branch requires zero modification when variables are added.

**Performance.** The parse-time speedup of option B is negligible at this scale (single-expression CLI tool). The overhead of one dict lookup per constant reference is immeasurable.

### Conclusion

```python
# New AST node (parser.py)
@dataclass
class Name:
    id: str   # e.g. "pi", "e", future "x"
```

The parser emits `Name(id)` whenever it sees an `IDENT` token **not** followed by `LPAREN`. Prior research (#38, #43) established this one-token look-ahead rule in `_parse_primary`.

---

## Q2 — Symbol Table Location

**Decision: module-level `dict[str, float]` in `evaluator.py`, pre-seeded with `pi` and `e`; passed as a default-valued parameter to `evaluate()`.**

### Options considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **A — Module-level dict, default param** | `ENV: dict[str, float]` at top of `evaluator.py`; `evaluate(node, env=ENV)` | ✓ Recommended |
| **B — `Context` object passed to `evaluate()`** | `evaluate(node, ctx: Context)` where `Context` wraps the dict | ✗ Over-engineered for v0.2.0 |
| **C — Class-based `Evaluator`** | `Evaluator(env).evaluate(node)` | ✗ Requires changing all call sites |

### Rationale for A

**Minimal callsite impact.** The existing `evaluate(node)` call signature in `__main__.py` and in every test continues to work unchanged when `env` defaults to the module-level constant table. No test or CLI code needs updating.

**Ready for variables.** When `x = 5` is added in a future version, the REPL or multi-statement runner will create a fresh mutable dict (or copy `ENV`) and pass it explicitly as `evaluate(node, user_env)`. The signature already supports this.

**Avoids wrapper overhead.** Option B (a `Context` class) adds no semantic value over a plain dict for the v0.2.0 scope. The spec mentions no features (scoping, closures, namespacing) that would justify a richer context object.

### Module-level constant table

```python
# evaluator.py
import math

_DEFAULT_ENV: dict[str, float] = {
    "pi": math.pi,
    "e":  math.e,
}
```

This dict is read-only in v0.2.0 (no assignment operator exists). A future assignment implementation will pass a caller-owned dict instead of `_DEFAULT_ENV`.

---

## Q3 — Function vs. Constant Namespace Conflict

**Decision: two separate namespaces; functions cannot shadow constants, and constants cannot shadow functions.**

### Options considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **A — Separate namespaces (env dict + function table)** | `Name` nodes look up `env`; `FunctionCall` nodes look up `_FUNCTION_TABLE` | ✓ Recommended |
| **B — Single unified namespace, variables shadow constants** | All names (constants, functions, variables) in one dict; user can assign `log = 5` | ✗ Rejected |

### Rationale for A

**Grammar enforces the separation.** The parser already distinguishes `IDENT LPAREN` (→ `FunctionCall`) from bare `IDENT` (→ `Name`). These are different AST node types dispatched independently. There is no path by which a constant lookup reaches the function table or vice versa.

**Prevents confusing shadowing.** If a user later writes `log = 5`, option B would silently break `log(x)` calls. With option A, the function table is never consulted for `Name` nodes, so `log = 5` creates a variable that does not affect the `log(x)` function dispatch.

**No parser rewrite to switch later.** Option B would require collapsing `FunctionCall` and `Name` into a single node type with runtime dispatch — that is the parser change the spec prohibits. Keeping them separate now means the choice cannot accidentally be reversed without a deliberate grammar change.

### Namespace conflict rules (v0.2.0)

| Input | AST node | Lookup path | Error if not found |
|-------|----------|-------------|-------------------|
| `pi` | `Name("pi")` | `env` dict | `UnknownName` |
| `log(1)` | `FunctionCall("log", [...])` | `_FUNCTION_TABLE` | `UnknownFunction` |
| `log` (bare) | `Name("log")` | `env` dict | `UnknownName` (not `UnknownFunction`) |

A bare `log` with no arguments is not a function-call syntax error at parse time — it parses as `Name("log")` — but it will raise `UnknownName` at evaluation time because `"log"` is not in `env`. This is acceptable: the spec's error case for an unrecognised constant is not specified, and `UnknownName` is a reasonable fallback.

---

## Q4 — Evaluator Signature Change

**Decision: add `env` as a keyword argument with a default, keeping the existing call signature valid.**

### Proposed signature

```python
def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
    if env is None:
        env = _DEFAULT_ENV
    ...
```

### Impact analysis

| Call site | Current call | After change | Needs update? |
|-----------|-------------|--------------|---------------|
| `__main__.py` | `evaluate(ast)` | `evaluate(ast)` | No |
| `tests/test_evaluator.py` | `evaluate(Parser(...).parse())` | unchanged | No |
| Future variable REPL | (not yet written) | `evaluate(ast, user_env)` | N/A |

**No existing call sites require modification.** The default `env=None` → `_DEFAULT_ENV` pattern is idiomatic Python and well-understood.

### Why not `env=_DEFAULT_ENV` directly as the default value?

Using a mutable dict as a default argument value is a Python antipattern: all callers would share the same object, and a future mutation would corrupt the default. Using `None` as sentinel and substituting inside the function body avoids this hazard at zero cost.

---

## Summary of Decisions

| Question | Decision |
|----------|----------|
| **AST node for constants** | `Name(id: str)` — eval-time dict lookup, same node future variables will use |
| **Symbol table location** | Module-level `_DEFAULT_ENV: dict[str, float]` in `evaluator.py`, seeded with `pi` and `e` |
| **Function vs. constant namespace** | Separate: `env` dict for `Name` nodes; `_FUNCTION_TABLE` for `FunctionCall` nodes |
| **evaluate() signature** | `evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float` — default keeps all existing call sites unchanged |

---

## Planned `evaluate()` Signature for v0.2.0

```python
def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
    if env is None:
        env = _DEFAULT_ENV

    if isinstance(node, Number):
        return node.value

    if isinstance(node, Name):
        value = env.get(node.id)
        if value is None:
            raise UnknownName(node.id)
        return value

    if isinstance(node, FunctionCall):
        entry = _FUNCTION_TABLE.get(node.name)
        if entry is None:
            raise UnknownFunction(node.name)
        if len(node.args) != entry.arity:
            raise WrongArity(node.name, entry.arity)
        evaluated_args = [evaluate(arg, env) for arg in node.args]
        if entry.domain_check is not None and not entry.domain_check(*evaluated_args):
            raise DomainError()
        result = entry.fn(*evaluated_args)
        _check_overflow(result)
        return result

    if isinstance(node, UnaryOp) and node.op == '-':
        result = -evaluate(node.operand, env)
        _check_overflow(result)
        return result

    if isinstance(node, BinaryOp):
        left = evaluate(node.left, env)
        right = evaluate(node.right, env)
        ...  # existing arithmetic
```

All recursive calls thread `env` through. The public API `evaluate(node)` continues to work with zero changes at existing call sites.

---

## Follow-up Issues

- **Lexer:** add `IDENT` and `COMMA` token types; add `_scan_identifier()` (see #38).
- **Parser:** add `Name` and `FunctionCall` AST nodes; extend `_parse_primary()` with one-token look-ahead (see #38).
- **Evaluator:** add `_DEFAULT_ENV`, `_FUNCTION_TABLE`, and handle `Name` / `FunctionCall` nodes; add `UnknownName`, `UnknownFunction`, `WrongArity`, `DomainError` errors.
- **Tests:** update `test_evaluator.py` to cover `pi`, `e`, built-in functions, and error cases (existing tests require no change — `evaluate(node)` still works).
