# Parser Architecture Research — v0.1.0

**Issue:** #1
**Date:** 2026-03-04
**Status:** Complete

---

## Question

What expression parsing approach satisfies the v0.1.x four-operator scope while remaining directly extensible to named functions, variables, and multi-argument expressions planned for future versions — without requiring a parser rewrite?

---

## Recommendation

**Recursive descent parser with an AST.**

This approach best satisfies the v0.1.0 scope while providing a clear, low-friction extension path for all planned future features.

---

## Options Evaluated

### 1. Recursive Descent (hand-written)

A set of mutually recursive functions, each representing a grammar rule. Precedence is encoded by the call hierarchy: `parseExpr` → `parseTerm` → `parseFactor` → `parsePrimary`.

**Pros:**
- Zero dependencies; pure standard library.
- Grammar rules map directly to functions — readable, debuggable without tooling.
- Adding new precedence levels = inserting a new function in the call chain.
- Adding named functions = handling identifier tokens in `parsePrimary`, calling `parseFunctionCall`.
- Adding variables = same token type (identifier); assignment handled by a new top-level rule.
- Multi-argument calls = loop inside `parseFunctionCall` consuming comma-separated expressions.

**Cons:**
- Left-recursive grammars require refactoring (not a concern here; no left-recursive rules needed for this feature set).
- Adding many new infix operators with distinct precedence requires adding one function per level, which is slightly more verbose than a Pratt table.

**Extension cost:** Low. New operators, functions, and variables each require small, localized additions.

---

### 2. Pratt Parser (top-down operator precedence)

A table-driven approach where each token carries a binding power (precedence) and a pair of parse functions (null denotation for prefix, left denotation for infix).

**Pros:**
- Adding operators requires only a new table entry — no structural change.
- Elegant for operator-heavy languages with many precedence levels.
- Named functions as prefix operators fit naturally.

**Cons:**
- The mental model (nud/led/bp) is less obvious than named grammar functions, increasing cognitive overhead for a solo developer unfamiliar with the pattern.
- For four operators, the machinery is heavier than the problem warrants.
- Adds no concrete benefit over recursive descent for this feature set.

**Extension cost:** Low, but the initial investment is higher than it needs to be for v0.1.0 scope.

---

### 3. Parser Combinator Library

Compose parsers from small reusable building blocks (sequence, choice, many, etc.).

**Pros:**
- Expressive grammar definitions.
- Reusable combinator building blocks.

**Cons:**
- Any third-party combinator library violates the zero-external-runtime-dependencies constraint.
- Implementing combinators from scratch in the stdlib is non-trivial and produces no advantage over recursive descent for this scale.

**Verdict:** Eliminated. Conflicts with the no-external-dependencies constraint.

---

### 4. Yacc/Bison or Generator-Based

**Verdict:** Eliminated. Generator tooling is not part of the build constraints; overkill for a four-operator grammar.

---

## Grammar (v0.1.0)

```
expr     → term ( ('+' | '-') term )*
term     → factor ( ('*' | '/') factor )*
factor   → unary
unary    → '-' unary | primary
primary  → NUMBER | '(' expr ')'
```

This grammar is non-left-recursive and maps directly to four parsing functions.

---

## Extension Plan (future versions, no rewrite required)

### Named functions — e.g. `sin(x)`, `sqrt(9)`

Extend `primary` to handle identifier tokens:

```
primary  → NUMBER | '(' expr ')' | IDENT '(' arglist ')'
arglist  → expr ( ',' expr )*
```

Implementation: in `parsePrimary`, when the current token is an `IDENT` followed by `(`, call `parseFunctionCall(name)`, which loops consuming comma-separated `parseExpr()` calls until `)`.

No existing parsing functions change structure.

### Variables — e.g. `x = 5`, `x + 1`

Add a top-level rule above `expr`:

```
statement → IDENT '=' expr | expr
```

Identifier tokens in expression position (not followed by `=` or `(`) resolve to variable lookup in `parsePrimary`.

No existing functions change structure; one new function `parseStatement` is added above `parseExpr`.

### Multi-argument expressions

Already handled by `arglist` above. No additional structural change.

---

## Decision

**Adopt recursive descent with an explicit AST.**

Rationale:
- Satisfies all v0.1.0 success criteria.
- Each future feature (named functions, variables, multi-argument calls) maps to a localized, additive change — one new branch in `parsePrimary`, one new function in the call chain, or one new top-level rule.
- No external dependencies.
- The function-per-rule structure is the most maintainable for a solo developer: grammar rules have names, stack traces are readable, and debugging requires no special tooling.

---

## Acceptance Criteria Review

| Criterion | Met? | Notes |
|-----------|------|-------|
| Handles all v0.1.0 operators and precedence | Yes | Four-level call hierarchy encodes precedence |
| Shows extension path for functions and variables | Yes | See Extension Plan above |
| No external runtime dependencies | Yes | Pure stdlib |
| Understandable and maintainable by a solo developer | Yes | One function per grammar rule |
