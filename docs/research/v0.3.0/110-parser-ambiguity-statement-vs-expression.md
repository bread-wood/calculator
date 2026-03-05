# Research: Parser Ambiguity — Statement-Level Assignment vs Expression Starting with IDENT

**Issue**: #110
**Milestone**: v0.3.0
**Date**: 2026-03-05

---

## Background

The current `Parser.parse()` returns a single `ASTNode` (an expression).
v0.3 introduces a program grammar:

```
program    = statement { ';' statement }
statement  = IDENT '=' expression
           | expression
```

Both `x = 5` and `x + 1` begin with an `IDENT` token, requiring the parser to
decide which production to use at the start of each statement.

---

## Q1 — Lookahead strategy

**Question**: Is a second lookahead slot needed, or does the existing single-token
`_current` window suffice?

**Finding**: The existing architecture stores only `_current` (the token already
consumed from the lexer). A single additional peek — the token *after* `_current`
— is needed to distinguish `IDENT '='` from `IDENT <anything else>`.

The `Lexer` object is live after `Parser.__init__` and `_advance()` always calls
`_lexer.next_token()`. There are two clean options:

**Option A — peek helper (preferred)**
Add a `_peek: Token | None` slot that is lazily filled:

```python
class Parser:
    def __init__(self, lexer: Lexer) -> None:
        self._lexer = lexer
        self._current: Token = self._lexer.next_token()
        self._lookahead: Token | None = None   # filled on demand

    def _peek_next(self) -> Token:
        if self._lookahead is None:
            self._lookahead = self._lexer.next_token()
        return self._lookahead

    def _advance(self) -> Token:
        previous = self._current
        if self._lookahead is not None:
            self._current = self._lookahead
            self._lookahead = None
        else:
            self._current = self._lexer.next_token()
        return previous
```

`_peek_next()` is called only inside `_parse_statement()` when `_current` is
`IDENT`. The change is backward-compatible: all existing call-sites use only
`_current` and `_advance()`.

**Option B — backtracking**
Parse optimistically as an expression; if the result is a bare `Name` node and
`_current` is `EQUALS`, reinterpret as assignment. This avoids the lookahead
slot but couples assignment semantics into the expression layer and gives
confusing errors for `f(x) = 5`.

**Recommendation**: Option A. Structural change is minimal and isolated to the
constructor and `_advance()`; no existing parsing logic changes.

---

## Q2 — Where to dispatch

**Question**: New `_parse_statement()` method vs treating `=` as a lowest-
precedence operator inside `_parse_expr()`?

**Finding**:

| Approach | Pros | Cons |
|---|---|---|
| New `_parse_statement()` | Clean separation of statement grammar from expression grammar; easy to add future statement types (e.g. `print`, `def`); error messages can say "expected `;` after statement" | Tiny bit more code |
| `=` as lowest-precedence operator | No new method; `x = y = 5` works for free if desired | Assignment is not an expression in most calculator languages; chains like `(x=5)+1` become syntactically valid; errors say "unexpected token" in the wrong layer; hard to restrict to statement context |

**Recommendation**: Add `_parse_statement()`. It calls `_peek_next()` to check
for `IDENT '='`; if true it advances past both tokens and calls `_parse_expr()`.
Otherwise it falls through to `_parse_expr()` directly:

```python
def _parse_statement(self) -> Statement:
    if (self._current.type == TokenType.IDENT
            and self._peek_next().type == TokenType.EQUALS):
        name = self._advance().value   # consume IDENT
        self._advance()                # consume '='
        expr = self._parse_expr()
        return Assign(name=name, value=expr)
    return ExprStatement(expr=self._parse_expr())
```

This keeps the expression grammar untouched and makes future statement types
(e.g. `let`, `print`) straightforward one-line additions.

---

## Q3 — EOF / `;` after last statement

**Question**: Should a trailing `;` be accepted or rejected?

**Finding**: The grammar as stated is:

```
program = statement { ';' statement }
```

Strictly read, a trailing semicolon is rejected because `{ ';' statement }`
requires a `statement` after each `;`. Accepting `x = 5 ;` would require
the grammar to be:

```
program = statement { ';' statement } [ ';' ]
```

**Recommendation**: **Accept** trailing semicolons. This is the convention in
Python's `REPL`, SQL, and most shell-oriented tools — users naturally type
trailing semicolons, and rejecting them produces confusing errors with no
corresponding benefit. The implementation cost is one extra `_match(SEMICOLON)`
after the loop in `parse_program()`:

```python
while self._match(TokenType.SEMICOLON):
    if self._current.type == TokenType.EOF:
        break        # trailing semicolon — stop
    statements.append(self._parse_statement())
```

This is the only place the trailing-semicolon policy is encoded, making it
easy to tighten later if the spec changes.

---

## Q4 — `parse()` interface change

**Question**: Return `list[Statement]` from `parse()` (breaking), or add
`parse_program()` and deprecate `parse()`?

**Finding**: There is exactly one call-site for `parse()`:
`__main__.py` line 29 (`ast = Parser(lexer).parse()`). The evaluator
(`evaluate(ast)`) currently accepts a single `ASTNode`. Both will need to
change for v0.3 regardless of which strategy is chosen.

| Strategy | Breaking change | Migration path |
|---|---|---|
| Change `parse()` → `list[Statement]` | Yes — current callers break immediately | Update `__main__.py` and evaluator in same PR |
| Add `parse_program()`, keep `parse()` | No | Gradual; leaves dead code; requires a second PR to remove old method |

**Recommendation**: **Replace `parse()` with `parse_program()`** (rename, not
overload). There is only one call-site; the change is mechanical. Keeping the
old `parse()` alive under a different signature would require a stub that is
immediately dead code. The rename also signals clearly in git history where
the program-level grammar was introduced.

Concrete changes:
- `parser.py`: rename `parse()` → `parse_program()`, change return type to
  `list[Statement]`; add `Assign` and `ExprStatement` AST nodes; add `EQUALS`
  to `TokenType` in `lexer.py`
- `__main__.py`: call `parse_program()`, pass the resulting `list[Statement]`
  to a new `evaluate_program()` (or iterate and call `evaluate()` per
  statement, printing each `ExprStatement` result and binding `Assign` names
  in an environment dict)
- Tests: update any test that calls `.parse()` directly

---

## Summary of recommended changes

### `lexer.py`
- Add `EQUALS = auto()` to `TokenType`
- Add `"=": TokenType.EQUALS` to `_SINGLE_CHAR`

### `parser.py`
- Add `_lookahead: Token | None` slot + lazy `_peek_next()` + updated `_advance()`
- Add `Assign(name: str, value: ASTNode)` and `ExprStatement(expr: ASTNode)` dataclasses
- Add `Statement = Assign | ExprStatement` type alias
- Add `_parse_statement() -> Statement`
- Rename `parse() -> parse_program() -> list[Statement]`; loop over `;`-delimited
  statements, accept trailing `;`

### `__main__.py`
- Call `parse_program()`; iterate statements; for `ExprStatement` print result;
  for `Assign` bind to an environment dict (evaluator needs an `env` parameter)
