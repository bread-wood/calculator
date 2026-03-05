# Research: Parser Extensibility for Function-Call Syntax and Named Constants

**Issue:** #73
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Complete

---

## Summary

The v0.1.x parser extends cleanly to support `name(arg, ...)` function-call syntax and
bare-identifier constant references (`pi`, `e`) through purely additive changes. No existing
production rule, token type, AST node type, or method signature requires modification. The same
extension point is structurally identical to what a future user-defined variable (`x = 5`) will
use, so the user-variable path remains open without a parser rewrite.

---

## Q1 — Does the v0.1.x lexer have an identifier / name token type?

**No.** The v0.1.x lexer (`lexer.py`) defines nine `TokenType` members:

```
NUMBER  PLUS  MINUS  STAR  SLASH  LPAREN  RPAREN  EOF  UNKNOWN
```

`IDENT` does not exist. Any alphabetic character (e.g. the `s` in `sqrt`) reaches the
fall-through `return Token(TokenType.UNKNOWN, ch)` at `lexer.py:51`, emitting a separate
`UNKNOWN` token for *each* character.

### Required additions (additive only)

1. Add `IDENT = auto()` to the `TokenType` enum.
2. Add `COMMA = auto()` to the `TokenType` enum (required for multi-argument functions such as
   `pow(2, 10)` and `atan2(1, 1)`).
3. Add `','` → `COMMA` to `_SINGLE_CHAR`.
4. Add a dispatch branch in `Lexer.next_token()` before the UNKNOWN fall-through:

```python
if ch.isalpha() or ch == "_":
    return self._scan_ident()
```

5. Add the `_scan_ident()` helper (≈6 lines):

```python
def _scan_ident(self) -> Token:
    start = self._cursor
    while self._peek().isalnum() or self._peek() == "_":
        self._advance()
    return Token(TokenType.IDENT, self._input[start:self._cursor])
```

### Invasiveness assessment

**Not invasive.** All existing token types and their scanning paths are unchanged. The only
characters redirected from `UNKNOWN` to `IDENT` are alphabetic characters and `_` — none of the
characters currently tested by `test_unknown_character` (`@`) or `test_unknown_then_eof` (`$`) are
affected. The exponent-notation ambiguity (`1e10`) is also benign: `_scan_number` already consumes
the `e`/`E` character inside its own loop (`lexer.py:81–86`) before `next_token` can dispatch on
it, so the identifier branch is never reached for exponent suffixes.

Estimated diff: **~14 new lines, 0 deletions**.

---

## Q2 — Does the v0.1.x parser use recursive-descent or Pratt?

**Recursive-descent**, with five explicit precedence levels:

| Level | Method | Handles |
|-------|--------|---------|
| Expression | `_parse_expr` | `+`, `-` (left-associative) |
| Term | `_parse_term` | `*`, `/` (left-associative) |
| Factor | `_parse_factor` | (delegates to unary) |
| Unary | `_parse_unary` | prefix `-` (right-associative) |
| Primary | `_parse_primary` | `NUMBER`, `'(' expr ')'` |

### Grafting primary → IDENT productions

With recursive-descent, a new `IDENT` branch appended to `_parse_primary` is sufficient. No other
production method changes.

**Extended grammar:**

```
primary → NUMBER
         | '(' expr ')'
         | IDENT '(' arglist ')'    ← new: function call
         | IDENT                    ← new: named constant / variable

arglist → ε
         | expr (',' expr)*
```

**Implementation — new branch in `_parse_primary` (≈7 lines):**

```python
if self._current.type == TokenType.IDENT:
    name = self._advance().value
    if self._current.type == TokenType.LPAREN:
        self._advance()              # consume '('
        args = self._parse_arglist()
        self._expect(TokenType.RPAREN)
        return Call(func=name, args=args)
    return Name(name=name)
```

**New AST nodes:**

```python
@dataclass
class Name:
    name: str          # bare identifier: pi, e, future x

@dataclass
class Call:
    func: str          # function name: sqrt, abs, pow …
    args: list[ASTNode]

ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

**New `_parse_arglist` helper (≈8 lines):**

```python
def _parse_arglist(self) -> list[ASTNode]:
    args: list[ASTNode] = []
    if self._current.type == TokenType.RPAREN:
        return args          # empty arglist: f()
    args.append(self._parse_expr())
    while self._current.type == TokenType.COMMA:
        self._advance()
        args.append(self._parse_expr())
    return args
```

`_parse_expr`, `_parse_term`, `_parse_factor`, and `_parse_unary` are **not touched**. The full
unary/factor chain already bottoms out in `_parse_primary`, so all nested expressions inside
argument lists (`sqrt(pow(3,2) + pow(4,2))`) parse correctly with no further changes.

Estimated parser diff: **~25 new lines, 0 deletions**.

---

## Q3 — Does the extension foreclose the user-variable path?

**No.** The `Name(name: str)` AST node is identical for built-in constants and future user
variables. The parser emits `Name("pi")` and `Name("x")` through the same code path; the
distinction is resolved at evaluation time via the environment dict, not in the parser.

### Design that keeps the variable path open

The evaluator will carry an `env: dict[str, float]` parameter pre-seeded with `{"pi": math.pi, "e": math.e}`:

```python
def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
    if env is None:
        env = _DEFAULT_ENV
    ...
    if isinstance(node, Name):
        if node.name not in env:
            raise UnknownName(node.name)
        return env[node.name]
```

When `x = 5` is added in v0.3.x:
- The assignment produces a *new top-level statement* (`Assign` node) — a grammar addition, not a
  change to the identifier production.
- The REPL/runner passes a caller-owned mutable dict: `evaluate(ast, user_env)`.
- The `Name` lookup branch in `evaluate()` is **unchanged**; it simply finds `x` in the
  caller-supplied dict instead of in `_DEFAULT_ENV`.

**Critical non-foreclosing property:** constants are resolved in the *evaluator*, not in the lexer
or parser. The alternative of emitting `pi` and `e` as literal `NUMBER` tokens from the lexer
(parse-time constant folding) would couple the two layers and block user variables, because the
parser cannot know the value of `x` at parse time. That approach was explicitly considered and
rejected in prior research (#56).

---

## Q4 — Disambiguation rule for bare IDENT vs. function call

**Rule:** if the token immediately following the consumed `IDENT` is `LPAREN`, it is a function
call; otherwise it is a name reference (constant or variable).

```
IDENT LPAREN …  →  Call node
IDENT           →  Name node
```

### Unambiguity proof

1. **No zero-argument functions in scope.** The v0.2.0 spec defines no zero-argument functions.
   `pi` and `e` are constants, not zero-arg calls. The grammar therefore has no case where a bare
   `IDENT` could be either a function call or a constant depending on context.

2. **One token of look-ahead is sufficient.** After consuming the `IDENT` token, `self._current`
   already holds the next token (the parser always pre-fetches one token). No additional buffering
   is required.

3. **No conflict with the existing `LPAREN` grouping path.** The existing `_parse_primary` branch
   for `LPAREN` is reached only when the *first* token of a primary is `LPAREN` (grouped
   expression). The function-call path is reached when the *first* token is `IDENT` and the
   *second* token is `LPAREN`. These are disjoint start conditions; no conflict exists.

4. **Future zero-arg functions (if ever added) would not break the rule** — they would just need
   to be written as `rand()` (with parens), which is the universal convention. The bare-IDENT path
   is reserved for name references.

The rule is unambiguous in the v0.1.x grammar context.

---

## Extension Point Summary

| Layer | Change type | Lines (est.) | Existing code modified? |
|-------|------------|--------------|------------------------|
| **Lexer** | Add `IDENT`, `COMMA` to `TokenType`; add `_scan_ident()`; add comma to `_SINGLE_CHAR`; add dispatch branch | +14 | No |
| **Parser** | Add `Name`, `Call` dataclasses; update `ASTNode` alias; add `IDENT` branch in `_parse_primary`; add `_parse_arglist` helper | +25 | No |
| **Evaluator** | Add `_DEFAULT_ENV` dict; add `_FUNCTION_TABLE`; handle `Name` and `Call` nodes; add new error types | +~40 | No (new `env` param uses default) |

**Total: ~79 additive lines. Zero existing lines deleted or restructured.**

---

## Confirmation: User-Variable Path Remains Open

The v0.2.0 design does **not** foreclose the `x = 5` path:

- The `Name(name)` AST node is the node future user variables will produce.
- The evaluator's `env` dict is the lookup mechanism future variable assignment will populate.
- The parser does not hard-code constant lookup; it emits `Name` nodes and defers resolution.
- Adding assignment syntax requires a new grammar production (`statement → IDENT '=' expr`), which
  is an addition, not a change to the identifier-reference or function-call productions established
  in v0.2.0.

---

## Follow-up Issues

- **Lexer implementation:** add `IDENT` and `COMMA` token types; add `_scan_ident()`.
- **Parser implementation:** add `Name` and `Call` AST nodes; extend `_parse_primary()`; add
  `_parse_arglist()`.
- **Evaluator implementation:** add `_DEFAULT_ENV`, `_FUNCTION_TABLE`, `UnknownName`,
  `UnknownFunction`, `WrongArity`, `DomainError`; handle new node types.
- **Tests:** lexer IDENT tokens, parser `Name`/`Call` nodes, evaluator function dispatch and
  error paths.
