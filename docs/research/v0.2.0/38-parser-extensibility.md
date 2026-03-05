# Research: Can v0.1.x Parser Extend to Function-Call Syntax and Named Constants?

**Issue:** #38
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Complete

---

## 1. v0.1.x Parser Strategy

The parser is a classic **recursive-descent** parser with explicit precedence levels:

| Level | Method | Handles |
|-------|--------|---------|
| Expression | `_parse_expr` | `+`, `-` (left-assoc) |
| Term | `_parse_term` | `*`, `/` (left-assoc) |
| Factor | `_parse_factor` | (delegates to unary) |
| Unary | `_parse_unary` | prefix `-` (right-assoc) |
| Primary | `_parse_primary` | NUMBER, `(` expr `)` |

It produces a typed AST with three node types: `Number`, `BinaryOp`, `UnaryOp`.

**Grammar (informal BNF):**
```
expr    → term ( ('+' | '-') term )*
term    → factor ( ('*' | '/') factor )*
factor  → unary
unary   → '-' unary | primary
primary → NUMBER | '(' expr ')'
```

---

## 2. Token Inventory

**Current `TokenType` enum (lexer.py):**

| Token | Symbol |
|-------|--------|
| NUMBER | digits / decimal / scientific |
| PLUS | `+` |
| MINUS | `-` |
| STAR | `*` |
| SLASH | `/` |
| LPAREN | `(` |
| RPAREN | `)` |
| EOF | (end of input) |
| UNKNOWN | (any unrecognised char) |

**IDENTIFIER is NOT a token type.** Any alphabetic character (e.g., `s` in `sqrt`) currently produces `UNKNOWN` tokens, one per character. The lexer has no identifier-scanning path.

**COMMA is NOT a token type.** The comma character `,` also produces `UNKNOWN`.

---

## 3. Answers to Research Questions

### Q1: Does the lexer produce IDENTIFIER tokens?

**No.** The lexer has no `IDENTIFIER` token type and no identifier-scanning loop. Adding identifiers requires:

1. Add `IDENTIFIER = auto()` to `TokenType`.
2. Add `COMMA = auto()` to `TokenType`.
3. Add `,` to `_SINGLE_CHAR` mapping.
4. Add a branch in `Lexer.next_token()` for `ch.isalpha() or ch == '_'` that scans `[A-Za-z_][A-Za-z0-9_]*` (analogous to `_scan_number`).

These are **additive changes only** — no existing token types are removed or altered. The existing `UNKNOWN` fallback is unchanged.

### Q2: Can the parser parse `NAME '(' arglist ')` without restructuring the grammar?

**Yes, with a minor additive extension.** The current `_parse_primary` method already handles the `(` case for grouping. Function-call syntax requires a new branch in `_parse_primary`:

```
primary → NUMBER
         | '(' expr ')'
         | IDENTIFIER '(' arglist ')'   ← new
         | IDENTIFIER                   ← new (named constant)

arglist → expr (',' expr)*
```

This is a straightforward extension of `_parse_primary` — no existing production changes. The new branch is entered only when the current token is `IDENTIFIER`, which is a new token type that previously didn't exist. **There is no ambiguity introduced into the existing grammar.**

### Q3: Does the grammar conflict on `(`?

**No conflict.** The current grammar only encounters `(` in `_parse_primary` where it means grouping. Under the proposed extension, when the parser is in `_parse_primary`:

- `NUMBER` → existing numeric literal path
- `LPAREN` → existing grouping path (unchanged)
- `IDENTIFIER` → new path: peek at next token
  - If next token is `LPAREN`: function call
  - Otherwise: named constant

This requires **one token of lookahead** (already available since the parser holds `self._current` and can call `self._lexer.next_token()` on demand, or alternatively use a two-token lookahead buffer). Since the parser currently holds one pre-fetched token (`self._current`), distinguishing `sqrt(` (function call) from a bare `pi` (constant) requires peeking at the token *after* the IDENTIFIER. The implementation can buffer one additional token without any architectural change.

### Q4: Named constants — zero-arg calls, lexer literals, or identifier-lookup?

**Cleanest fit: identifier-lookup phase at evaluation time.**

Options assessed:

| Approach | Pros | Cons |
|----------|------|------|
| Lexer emits `PI`/`E` as NUMBER tokens | No parser change | Hardcodes constants in lexer; breaks user-defined variables |
| Zero-arg function call `pi()` | Uniform function AST | Non-standard syntax; ugly UX |
| New `Identifier` AST node + evaluator lookup table | Clean separation; extensible to variables | Requires new AST node type |

**Recommended:** Emit `IDENTIFIER` tokens from the lexer; introduce an `Identifier` AST node in the parser; resolve names (built-in constants + future user variables) in the evaluator via a lookup table. This is additive to all three layers.

### Q5: Does function-call extension consume the identifier hook for future variables?

**No.** The same `IDENTIFIER` token type and `Identifier` AST node serve both use cases:

- `pi` (no following `(`): evaluates as a named constant (lookup table in evaluator)
- `x` (no following `(`): future user variable (same lookup table, populated by assignment)
- `sqrt(9)` (followed by `(`): evaluates as a function call

Assignment syntax (`x = 5`) would require a new top-level statement production in the parser, but it does **not** conflict with the function-call extension. The identifier hook is shared, not consumed.

---

## 4. Verdict

**Extend cleanly — minor additive changes only, no restructuring required.**

The v0.1.x parser was designed with the extensibility constraint met. The changes needed for v0.2.0 are:

### Lexer changes (additive)
- Add `IDENTIFIER` and `COMMA` to `TokenType`.
- Add `','` to `_SINGLE_CHAR`.
- Add `_scan_identifier()` method and dispatch branch in `next_token()`.

### Parser changes (additive)
- Add `FunctionCall` and `Identifier` dataclasses to the AST node union.
- Extend `_parse_primary()` with an `IDENTIFIER` branch:
  - If next token is `LPAREN`: parse arg list, emit `FunctionCall` node.
  - Else: emit `Identifier` node.
- Add `_parse_arglist()` helper using `COMMA` as separator.
- Update `ASTNode` union type alias.

### Evaluator changes (additive)
- Add a `CONSTANTS` dict (`{"pi": math.pi, "e": math.e, ...}`).
- Add a `FUNCTIONS` dict (`{"sqrt": math.sqrt, "pow": math.pow, ...}`).
- Handle `Identifier` and `FunctionCall` node types in `evaluate()`.

### No changes required to
- Grammar structure / precedence levels
- Existing token types
- Existing AST node types (`Number`, `BinaryOp`, `UnaryOp`)
- Error hierarchy (new `UnknownIdentifier` / `WrongArgCount` errors may be added but existing ones are untouched)

---

## 5. Minimum Viable Change Summary

```
lexer.py   : +IDENTIFIER, +COMMA token types; +_scan_identifier(); +comma dispatch
parser.py  : +Identifier, +FunctionCall AST nodes; extend _parse_primary(); +_parse_arglist()
evaluator.py: +CONSTANTS dict; +FUNCTIONS dict; handle new node types in evaluate()
```

Total estimated diff: ~60–80 lines across three files. No existing lines need to be deleted or restructured.

---

## 6. Follow-up Issues

The following implementation issues should be spawned from this research:

1. **Lexer: add IDENTIFIER and COMMA tokens** — implement `_scan_identifier()` and update `TokenType`.
2. **Parser: add function-call and named-constant AST nodes** — extend `_parse_primary()` and add `_parse_arglist()`.
3. **Evaluator: built-in functions and constants** — `sqrt`, `pow`, `abs`, `pi`, `e`; argument-count validation; new error types `UnknownIdentifier` and `WrongArgCount`.
4. **Tests: function-call and named-constant coverage** — unit tests across all three layers.
