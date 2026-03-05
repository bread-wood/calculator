# Research: Constant vs Function Namespace Design for Future Variable Extensibility

**Issue:** #43
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## 1. Current State (v0.1.x)

The v0.1.x lexer recognises only: `NUMBER`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `LPAREN`, `RPAREN`, `EOF`, `UNKNOWN`. There are no `IDENT` or `CONST` tokens. Adding named constants and functions in v0.2.0 requires a new token type regardless of the design choice; the question is which design best serves future variable extensibility.

---

## 2. Token Type: IDENT for all named identifiers

**Recommendation: add a single `IDENT` token type to the lexer. Use it for constants (`pi`, `e`), built-in functions (`sqrt`, `log`, …), and future user variables (`x`, `y`, …) alike.**

### Why not a dedicated CONST token?

- A `CONST` token would require the *lexer* to carry a hard-coded list of constant names. The lexer's job is character classification, not semantic lookup.
- When user variables arrive, the lexer cannot know at scan time whether an identifier is a constant, a built-in function, or a user variable. Introducing a separate `CONST` token now means eliminating it (or broadening it) when variables are added — that is the parser rewrite the spec explicitly wants to avoid.
- `IDENT` is the standard approach in every major language and keeps the lexer context-free.

### Why not zero-argument function calls?

- Representing `pi` as `pi()` diverges from every mathematical convention and from the spec's acceptance criteria (`calc 'pi'` must work without parentheses).
- It also makes `2 * pi` awkward: the grammar would need a production that allows an IDENT-without-parens only for specific names — which is context-sensitive and requires a lookup in the parser, coupling the parser to the symbol table anyway.

### Conclusion

Add to `TokenType`:

```python
IDENT = auto()
```

The lexer scans any sequence of `[a-zA-Z_][a-zA-Z0-9_]*` as `Token(TokenType.IDENT, lexeme)`. No name-based branching in the lexer.

---

## 3. Symbol Table / Environment Design

**Recommendation: a single unified symbol table with an immutable (read-only) flag per entry, bootstrapped with built-in constants.**

### Structure

```python
from dataclasses import dataclass, field
from typing import Final

@dataclass
class Symbol:
    value: float
    readonly: bool = True   # True for built-ins; False for user variables (future)

# Global environment — module-level singleton for v0.2.0
CONSTANTS: dict[str, Symbol] = {
    "pi": Symbol(value=3.141592653589793, readonly=True),
    "e":  Symbol(value=2.718281828459045, readonly=True),
}
```

The evaluator receives (or has access to) this table. In v0.2.0 it is read-only bootstrapped; the write path (`x = 5`) is added in the future assignment version without touching the parser.

### Why unified rather than a separate constants map?

| Concern | Separate constants map | Unified symbol table |
|---|---|---|
| Future variable lookup | Requires merging two dicts at lookup time | Single dict lookup |
| Shadowing protection | Enforced by keeping maps separate | Enforced by `readonly` flag |
| Parser coupling | Same — parser emits IDENT either way | Same |
| Code complexity | Two lookup paths | One lookup path |

A separate constants map would need to be consulted at every variable lookup anyway (to handle `2 * pi` after a user writes `x = 2 * pi`). A unified table with a `readonly` flag is strictly simpler at lookup time and eliminates the merge step.

---

## 4. Distinguishing Constants from Functions at Parse/Eval Time

### Parse time

The parser emits:

- `IDENT` followed by `LPAREN` → `FuncCall` AST node (grammar rule, no symbol table lookup needed).
- `IDENT` **not** followed by `LPAREN` → `Identifier` AST node (constant or future variable).

This is a one-token lookahead rule in `_parse_primary` — completely mechanical, no symbol table consulted.

```python
# New AST nodes for v0.2.0
@dataclass
class Identifier:
    name: str          # e.g. "pi", "e", future "x"

@dataclass
class FuncCall:
    name: str
    args: list[ASTNode]
```

### Evaluation time

```python
# In evaluate():
if isinstance(node, Identifier):
    sym = env.get(node.name)
    if sym is None:
        raise UnknownName(node.name)   # or UnknownFunction depending on error spec
    return sym.value

if isinstance(node, FuncCall):
    fn = FUNCTION_TABLE.get(node.name)
    if fn is None:
        raise UnknownFunction(node.name)
    return fn(node.args, env)
```

Constants and future user variables share the same `Identifier` → `env` lookup. Functions use a **separate** dispatch table (`FUNCTION_TABLE`) keyed by name.

**Why keep functions in a separate dispatch table?**

- Functions carry arity metadata and a callable; constants carry only a float.
- The spec says "adding a new function requires adding one entry to the table, not modifying the parser" — a dedicated `FUNCTION_TABLE` dict satisfies this exactly.
- It also prevents a user from accidentally shadowing `sqrt` with `sqrt = 5` in a future version (the parser grammar already disambiguates based on presence/absence of `(`; but the separate table makes the intent explicit).

---

## 5. Read/Write Story for v0.2.0

- **Bootstrap (v0.2.0):** `CONSTANTS` dict is populated once at import time. No write path exists; attempting to assign to a `readonly` symbol raises `AssignmentToConstant` (which need not be surfaced until the assignment feature is built).
- **Future assignment:** An assignment operator (`=`) will be scanned as a new `ASSIGN` token. The parser will emit an `Assignment` AST node. The evaluator will check `sym.readonly` before writing. No grammar rule for `Identifier` or `FuncCall` changes.

---

## 6. Conflict Check with v0.1.x Tokens

The existing v0.1.x `TokenType` enum has no `IDENT`, no `CONST`, and no reserved-word tokens. The characters `[a-zA-Z_]` currently fall through to `UNKNOWN`. Adding `IDENT` is additive and backward-compatible: the only change is that the lexer's `next_token()` gains a new branch before the `UNKNOWN` fallthrough.

Neither `pi` nor `e` conflicts with any existing operator token. The exponent scan in `_scan_number` consumes `e`/`E` only when they are part of a numeric literal context (digits before them). A standalone `e` or `pi` identifier is correctly scanned as `IDENT` because the number scanner is only entered when `ch.isdigit() or ch == "."`.

**Edge case:** `1e2` (scientific notation) vs `e` identifier. The existing `_scan_number` handles `1e2` as a single NUMBER token because the scanner is entered on `1` (a digit). `e` standing alone (cursor on `e` with no preceding digit) goes to the IDENT branch. No conflict.

---

## 7. Composability Test: `2 * pi`

Parse trace:
1. Lexer emits: `NUMBER("2")`, `STAR("*")`, `IDENT("pi")`, `EOF`
2. `_parse_expr` → `_parse_term`
3. `_parse_term` → left = `Number(2.0)`, sees `STAR`, advances, right = `_parse_factor()`
4. `_parse_factor` → `_parse_unary` → `_parse_primary`
5. `_parse_primary`: current token is `IDENT("pi")`, peek-ahead is `EOF` (not `LPAREN`) → emits `Identifier("pi")`
6. `_parse_term` returns `BinaryOp("*", Number(2.0), Identifier("pi"))`
7. Evaluation: `evaluate(BinaryOp)` → `2.0 * env["pi"].value` = `2.0 * 3.141592653589793` = `6.283185307179586` ✓

---

## 8. Summary of Recommendations

| Decision | Recommendation |
|---|---|
| Token type for `pi`, `e`, future `x` | `IDENT` — single token type for all named identifiers |
| Where constants are stored | Unified symbol table (`dict[str, Symbol]`) with `readonly=True` |
| Function registry | Separate `FUNCTION_TABLE: dict[str, Callable]` |
| Parse-time disambiguation (constant vs function) | Grammar rule: `IDENT LPAREN` → `FuncCall`; `IDENT` → `Identifier` |
| Eval-time lookup | Constants/variables → symbol table; functions → function table |
| v0.2.0 write access | None; `readonly` flag enforced at eval time (not yet surfaced as user error) |
| Future variable compatibility | Add `ASSIGN` token + `Assignment` AST node; no parser grammar changes required |

This design satisfies the spec constraint: the constant and function namespaces are extensible to user-defined variables in a future version without a parser rewrite.
