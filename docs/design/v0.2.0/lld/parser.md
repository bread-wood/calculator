# Low-Level Design — Parser Module (v0.2.0)

**Module:** `parser`
**File:** `src/calc/parser.py`
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Draft

---

## 1. Responsibility

The parser consumes a token stream from `Lexer` and produces a typed Abstract Syntax Tree (AST) representing the expression's grammatical structure. v0.2.0 extends the v0.1.0 parser with two new AST node types (`Name`, `Call`) and one new private helper (`_parse_arglist`), all confined to additions inside `_parse_primary`. The parser enforces grammar rules, operator precedence, and associativity. It does **not** resolve names, validate arity, check domains, perform evaluation, or write to stdout/stderr.

**Scope boundary:** The parser does not know which identifiers are valid constants or functions. It emits a `Name` node for any bare identifier and a `Call` node for any `ident(...)` expression; semantic validation (unknown name, wrong arity) is the evaluator's responsibility.

---

## 2. Public Interface

### 2.1 AST Node Types

All node types are `dataclass` instances with structural equality (`==`) provided for free. The `ASTNode` union type alias documents the complete set of valid nodes for the evaluator.

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Number:
    value: float           # parsed float literal

@dataclass
class BinaryOp:
    op: str                # one of: '+', '-', '*', '/'
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str                # only '-' in v0.2.0
    operand: ASTNode

@dataclass
class Name:                # NEW v0.2.0 — bare identifier (constant or future variable)
    name: str              # raw lexeme, e.g. "pi", "e"

@dataclass
class Call:                # NEW v0.2.0 — function-call expression
    func: str              # function name lexeme, e.g. "sqrt", "pow"
    args: list[ASTNode]    # positional arguments (zero or more)

ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

**Rationale for `Name` (eval-time lookup, not parse-time folding):** The parser holds no symbol table. Using a `Name` node keeps the parser table-agnostic and allows the same token and node type to serve future user variables without any parser change (research #43, #56).

**Rationale for `Call.args: list[ASTNode]`:** Storing arguments as a plain list of `ASTNode` is sufficient; no wrapper type is needed. The evaluator validates the count.

### 2.2 Parser Class

```python
class Parser:
    def __init__(self, lexer: Lexer) -> None: ...
    def parse(self) -> ASTNode: ...
```

**`Parser(lexer: Lexer)`** — constructs a parser and pre-fetches the first token into `_current` by calling `_advance()` once.

**`Parser.parse() -> ASTNode`** — entry point; calls `_parse_expr()`, asserts `_current.type == TokenType.EOF`, and returns the root node. Raises `UnexpectedToken` if any token follows a complete expression (e.g., `2 3`).

### 2.3 Error Types Raised

| Error | Condition |
|---|---|
| `UnexpectedToken` | Wrong token where an operand or closing paren is expected |
| `UnexpectedEnd` | EOF reached before expression or closing `)` is complete |

No new error types are raised by the parser in v0.2.0. Semantic errors (`UnknownFunction`, `WrongArity`, `DomainError`) are raised by the evaluator, not the parser.

---

## 3. Data Structures

### 3.1 Parser State

```python
class Parser:
    _lexer: Lexer
    _current: Token   # next unconsumed token (one-token lookahead)
```

The parser maintains exactly one token of lookahead. No multi-token buffer is needed because the grammar is LL(1) with respect to the parser's decision points:

- `IDENT` followed by `LPAREN` → `Call` (the `LPAREN` is checked via `self._current` *after* the IDENT is consumed, so no extra peek is required).
- `IDENT` not followed by `LPAREN` → `Name`.

This avoids any change to the lookahead mechanism (research #38, #53, #73).

---

## 4. Grammar

v0.2.0 adds one new production (`primary → IDENT ...`) and one helper rule (`arglist`):

```
expr     → term ( ('+' | '-') term )*
term     → factor ( ('*' | '/') factor )*
factor   → unary
unary    → '-' unary | primary
primary  → NUMBER
          | '(' expr ')'
          | IDENT '(' arglist ')'   ← new: function call
          | IDENT                   ← new: named constant / variable

arglist  → ε
          | expr ( ',' expr )*
```

All existing production rules are unchanged. The `factor` pass-through level is preserved as an extension seam for a future exponentiation operator.

**Grammar properties:**
- LL(1): the IDENT branch in `primary` requires one token of lookahead beyond the IDENT itself (peek at `LPAREN` vs. anything else). This lookahead is satisfied by reading `self._current` after consuming the IDENT token with `_advance()` — no buffer change needed.
- Left-associativity for `+`, `-`, `*`, `/` is preserved by the iterative `while` loops in `_parse_expr` and `_parse_term`.
- Right-associativity for unary negation is preserved by the recursive call in `_parse_unary`.

---

## 5. Key Algorithms and Logic

### 5.1 `_parse_primary` — IDENT Branch (new)

```python
def _parse_primary(self) -> ASTNode:
    if self._current.type == TokenType.NUMBER:
        value = float(self._advance().value)
        return Number(value=value)
    if self._current.type == TokenType.LPAREN:
        self._advance()
        node = self._parse_expr()
        self._expect(TokenType.RPAREN)
        return node
    if self._current.type == TokenType.IDENT:      # NEW
        name = self._advance().value
        if self._current.type == TokenType.LPAREN:
            self._advance()                        # consume '('
            args = self._parse_arglist()
            self._expect(TokenType.RPAREN)
            return Call(func=name, args=args)
        return Name(name=name)
    if self._current.type == TokenType.EOF:
        raise UnexpectedEnd()
    raise UnexpectedToken()
```

**Flow:**
```
_parse_primary
       │
       ├─ NUMBER  → Number(float(token.value))
       │
       ├─ LPAREN  → advance, _parse_expr(), _expect(RPAREN) → inner node
       │
       ├─ IDENT   → advance, consume name
       │       │
       │       ├─ LPAREN → advance '(', _parse_arglist(), _expect(')')  → Call(name, args)
       │       │
       │       └─ anything else                                          → Name(name)
       │
       ├─ EOF     → UnexpectedEnd
       │
       └─ other   → UnexpectedToken
```

**Why consume IDENT before peeking:** Consuming the IDENT first with `_advance()` makes `self._current` the token immediately after the identifier. No separate peek method or two-element buffer is required (research #53, #73).

### 5.2 `_parse_arglist` — New Private Helper

```python
def _parse_arglist(self) -> list[ASTNode]:
    args: list[ASTNode] = []
    if self._current.type == TokenType.RPAREN:
        return args                    # zero-argument call: f()
    args.append(self._parse_expr())
    while self._current.type == TokenType.COMMA:
        self._advance()                # consume ','
        args.append(self._parse_expr())
    return args
```

**Edge cases:**
- `f()` — `_current` is `RPAREN` immediately; returns `[]` without calling `_parse_expr`.
- `f(a)` — one expression parsed; `COMMA` not present; loop exits; returns `[a]`.
- `f(a, b)` — first expression parsed; `COMMA` consumed; second expression parsed; returns `[a, b]`.
- Trailing comma `f(a,)` — after the comma, `_parse_expr()` is called; `RPAREN` is neither a valid expression start nor a comma; raises `UnexpectedToken` (correct: trailing commas are not part of the spec grammar).

**Why COMMA is a first-class `TokenType`:** Consistency with every other syntactically meaningful single-char token; avoids coupling `_parse_arglist` to the `UNKNOWN` fallthrough (research #65, #77).

### 5.3 Token Advancement (unchanged from v0.1.0)

```python
def _advance(self) -> Token:
    previous = self._current
    self._current = self._lexer.next_token()
    return previous

def _match(self, *types: TokenType) -> bool:
    if self._current.type in types:
        self._advance()
        return True
    return False

def _expect(self, type: TokenType) -> Token:
    if self._current.type != type:
        if self._current.type == TokenType.EOF:
            raise UnexpectedEnd()
        raise UnexpectedToken()
    return self._advance()
```

These helpers are unchanged. `_expect` continues to centralize the EOF-vs-wrong-token disambiguation for closing parentheses.

---

## 6. Internal Structure

### 6.1 File Layout (`src/calc/parser.py`)

```
imports
  from __future__ import annotations
  from dataclasses import dataclass
  from calc.errors import UnexpectedEnd, UnexpectedToken
  from calc.lexer import Lexer, Token, TokenType

AST dataclasses
  Number, BinaryOp, UnaryOp      (unchanged from v0.1.0)
  Name, Call                     (new v0.2.0)

ASTNode type alias
  ASTNode = Number | BinaryOp | UnaryOp | Name | Call

Parser class
  __init__
  parse
  _advance
  _match
  _expect
  _parse_expr
  _parse_term
  _parse_factor
  _parse_unary
  _parse_primary                 (extended with IDENT branch)
  _parse_arglist                 (new v0.2.0)
```

No new files are introduced. The parser module remains a single file.

### 6.2 Private Helpers

| Helper | Purpose |
|---|---|
| `_advance()` | Consume current token; load next; return consumed token |
| `_match(*types)` | Consume and return `True` iff current token is one of `types`; used in operator loops |
| `_expect(type)` | Consume a mandatory token; raise `UnexpectedEnd`/`UnexpectedToken` on mismatch |
| `_parse_arglist()` | Parse zero-or-more comma-separated expressions between `(` and `)` |

---

## 7. Error Handling

The parser raises errors only from `_parse_primary` and `_expect`. No new error paths are introduced in v0.2.0; the IDENT branch uses the same `_expect(RPAREN)` call already used by the grouping branch.

| Condition | Error | Example |
|---|---|---|
| Token after complete expression | `UnexpectedToken` | `2 3` |
| EOF where operand expected | `UnexpectedEnd` | `2 +` |
| Wrong token where operand expected | `UnexpectedToken` | `2 + )` |
| EOF where `)` expected | `UnexpectedEnd` | `(2 + 3` or `sqrt(9` |
| Wrong token where `)` expected | `UnexpectedToken` | `(2 + 3 4` or `sqrt(9 4` |
| Bare IDENT with no following `(` | emits `Name` node — **not** an error at parse time |

The parser never raises `UnknownFunction`, `WrongArity`, or `DomainError`; those are evaluator concerns (research #54).

**Dependency error propagation:** `_parse_expr` calls `_parse_term` etc. down to `_parse_primary`; errors bubble up through the call stack without being caught or re-wrapped by the parser.

---

## 8. Testing Strategy

Tests live in `tests/test_parser.py`. All existing tests remain valid and green — no existing production rules change. New tests verify the two new node types and the arglist helper.

### 8.1 Existing Tests (unchanged)

All v0.1.0 tests for `Number`, `BinaryOp`, `UnaryOp`, precedence, associativity, and error paths remain. They do not use `IDENT` input and are unaffected by the new branch.

### 8.2 New Happy-Path Tests

| Expression | Expected AST |
|---|---|
| `"pi"` | `Name("pi")` |
| `"e"` | `Name("e")` |
| `"sqrt(9)"` | `Call("sqrt", [Number(9.0)])` |
| `"pow(2, 10)"` | `Call("pow", [Number(2.0), Number(10.0)])` |
| `"abs(0)"` | `Call("abs", [Number(0.0)])` |
| `"f()"` (zero args) | `Call("f", [])` |
| `"-pi"` | `UnaryOp("-", Name("pi"))` |
| `"sqrt(2 + 3)"` | `Call("sqrt", [BinaryOp("+", Number(2.0), Number(3.0))])` |
| `"pow(sqrt(4), 2)"` | `Call("pow", [Call("sqrt", [Number(4.0)]), Number(2.0)])` — nested call |
| `"2 * pi"` | `BinaryOp("*", Number(2.0), Name("pi"))` |

### 8.3 Error-Path Tests for New Cases

```python
@pytest.mark.parametrize("expr,error_type", [
    ("sqrt(",    UnexpectedEnd),    # unclosed paren after function
    ("sqrt(9",   UnexpectedEnd),    # missing closing paren
    ("sqrt(9 4", UnexpectedToken),  # missing comma / wrong token
])
def test_parse_errors_v0_2_0(expr, error_type):
    with pytest.raises(error_type):
        Parser(Lexer(expr)).parse()
```

### 8.4 Arglist Edge Cases

```python
def test_zero_arg_call():
    assert parse("f()") == Call("f", [])

def test_trailing_comma_is_error():
    with pytest.raises((UnexpectedEnd, UnexpectedToken)):
        parse("f(1,)")
```

### 8.5 What to Mock

Nothing. The parser is deterministic and pure; it depends only on the `Lexer`, which itself has no I/O. Tests construct a `Lexer` from a string literal and pass it directly to `Parser`. No mocking is needed or appropriate at this layer.

### 8.6 Coverage Target

All branches in `_parse_primary` (NUMBER, LPAREN, IDENT-with-LPAREN, IDENT-without-LPAREN, EOF, other) and both paths in `_parse_arglist` (zero args, one-or-more args) must be exercised. The tables above achieve this.

---

## 9. Dependencies

| Dependency | Direction | What is used |
|---|---|---|
| `src/calc/lexer.py` | import | `Lexer`, `Token`, `TokenType` (including new `IDENT`, `COMMA`) |
| `src/calc/errors.py` | import | `UnexpectedToken`, `UnexpectedEnd` |
| `src/calc/evaluator.py` | consumed by (one-way) | evaluator imports `ASTNode` types from `parser.py` |

The parser module has no circular imports. `errors.py` has no dependencies; `lexer.py` has no dependencies; `parser.py` depends on both.

`TokenType.IDENT` and `TokenType.COMMA` must be added to `lexer.py` before `parser.py` is extended (research #38, #43, #53, #65).
