# Low-Level Design — Parser Module (v0.1.0)

**Module:** `parser`
**File:** `src/calc/parser.py`
**Milestone:** v0.1.0
**Date:** 2026-03-04
**Status:** Draft

---

## 1. Responsibility

The parser consumes a token stream from the `Lexer` and produces an Abstract Syntax Tree (AST). It enforces grammar rules, operator precedence, and associativity. It raises `CalcError` subclasses on any syntax violation; it never writes to stderr.

---

## 2. Data Structures

### 2.1 AST Node Types

AST nodes are implemented as Python `dataclasses` (stdlib, no external dependencies). Using dataclasses over named tuples provides readable field names, `__repr__`, and easy future extension with optional fields (e.g., source position).

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Number:
    value: float

@dataclass
class BinaryOp:
    op: str          # one of: '+', '-', '*', '/'
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str          # only '-' in v0.1.0
    operand: ASTNode

ASTNode = Number | BinaryOp | UnaryOp
```

**Rationale:**
- `dataclass` gives structural equality (`==`) for free, which is essential for AST assertion tests.
- `op: str` stores the operator character directly; no separate operator enum is needed at this scale. The evaluator matches on `'+'`, `'-'`, `'*'`, `'/'`.
- The `ASTNode` union type alias documents the valid node types for the evaluator.

### 2.2 Parser State

```python
class Parser:
    _lexer: Lexer
    _current: Token   # most recently consumed token (lookahead)
```

The parser holds exactly one token of lookahead (`_current`). No token buffer or list is built. Tokens are consumed on demand by calling `_lexer.next_token()`.

---

## 3. Grammar

```
expr     → term ( ('+' | '-') term )*
term     → factor ( ('*' | '/') factor )*
factor   → unary
unary    → '-' unary | primary
primary  → NUMBER | '(' expr ')'
```

The call hierarchy encodes operator precedence: `+`/`-` are lowest (parsed in `_parse_expr`), `*`/`/` are next (parsed in `_parse_term`), unary negation is highest (parsed in `_parse_unary`), and grouping via parentheses resets precedence at `_parse_primary`.

The `factor` level is a pass-through to `unary` in v0.1.0; it exists as a named placeholder so that a future precedence level (e.g., exponentiation `**`) can be inserted between `term` and `unary` without restructuring the grammar.

---

## 4. Public API

```python
class Parser:
    def __init__(self, lexer: Lexer) -> None: ...
    def parse(self) -> ASTNode: ...
```

### `Parser(lexer: Lexer)`

Constructs a parser over the given lexer. Immediately calls `_advance()` to load the first token into `_current`. No tokens are consumed beyond the first lookahead.

### `Parser.parse() -> ASTNode`

Entry point. Calls `_parse_expr()`, then asserts that `_current.type == TokenType.EOF`. If a token remains after a complete expression is parsed (e.g., `2 3`), raises `UnexpectedToken`. Returns the root `ASTNode` on success.

---

## 5. Key Algorithms

### 5.1 Token Advancement

```python
def _advance(self) -> Token:
    previous = self._current
    self._current = self._lexer.next_token()
    return previous
```

Returns the just-consumed token. The invariant is that `_current` always holds the next unconsumed token.

### 5.2 Conditional Consumption

```python
def _match(self, *types: TokenType) -> bool:
    if self._current.type in types:
        self._advance()
        return True
    return False
```

Used in `_parse_expr` and `_parse_term` to consume an operator token only when it matches, supporting the `( op operand )*` loop pattern.

### 5.3 Mandatory Consumption

```python
def _expect(self, type: TokenType) -> Token:
    if self._current.type != type:
        if self._current.type == TokenType.EOF:
            raise UnexpectedEnd()
        raise UnexpectedToken()
    return self._advance()
```

Used in `_parse_primary` to consume the closing `)`. Distinguishes between EOF (raises `UnexpectedEnd`) and a wrong-token (raises `UnexpectedToken`) so that the error messages match the spec.

### 5.4 Parsing Functions

```python
def _parse_expr(self) -> ASTNode:
    node = self._parse_term()
    while self._current.type in (TokenType.PLUS, TokenType.MINUS):
        op = self._advance().value
        right = self._parse_term()
        node = BinaryOp(op=op, left=node, right=right)
    return node

def _parse_term(self) -> ASTNode:
    node = self._parse_factor()
    while self._current.type in (TokenType.STAR, TokenType.SLASH):
        op = self._advance().value
        right = self._parse_factor()
        node = BinaryOp(op=op, left=node, right=right)
    return node

def _parse_factor(self) -> ASTNode:
    return self._parse_unary()

def _parse_unary(self) -> ASTNode:
    if self._current.type == TokenType.MINUS:
        op = self._advance().value
        operand = self._parse_unary()
        return UnaryOp(op=op, operand=operand)
    return self._parse_primary()

def _parse_primary(self) -> ASTNode:
    if self._current.type == TokenType.NUMBER:
        value = float(self._advance().value)
        return Number(value=value)
    if self._current.type == TokenType.LPAREN:
        self._advance()
        node = self._parse_expr()
        self._expect(TokenType.RPAREN)
        return node
    if self._current.type == TokenType.EOF:
        raise UnexpectedEnd()
    raise UnexpectedToken()
```

**Left-associativity** for `+`, `-`, `*`, `/` is achieved by the iterative `while` loop in `_parse_expr` and `_parse_term`: the accumulator variable `node` is always on the left of the new `BinaryOp`.

**Right-associativity** for unary negation is achieved by the recursive call `_parse_unary()` on the operand, allowing `--5` to parse as `UnaryOp('-', UnaryOp('-', Number(5)))`.

---

## 6. Error Handling

| Condition | Error raised | Example input |
|---|---|---|
| Token after complete parse | `UnexpectedToken` | `2 3` |
| Expected operand, got EOF | `UnexpectedEnd` | `2 +` |
| Expected operand, got wrong token | `UnexpectedToken` | `2 + )` |
| Expected `)`, got EOF | `UnexpectedEnd` | `(2 + 3` |
| Expected `)`, got wrong token | `UnexpectedToken` | `(2 + 3 4` |

All errors are subclasses of `CalcError` (defined in `src/calc/errors.py`). The parser never writes to stderr or stdout. The caller (`__main__.py`) catches `CalcError` and formats the message.

The `_expect` helper centralizes the EOF-vs-wrong-token disambiguation so neither `_parse_primary` nor future parsing functions need to repeat the logic.

---

## 7. Extension Points

The HLD mandates that the parser must extend to named functions and variables without a rewrite. The following additions are localized and additive:

### Named functions (future)
Add `IDENT` to `TokenType` in `lexer.py`. In `_parse_primary`, add:
```python
if self._current.type == TokenType.IDENT:
    name = self._advance().value
    self._expect(TokenType.LPAREN)
    args = self._parse_arglist()
    self._expect(TokenType.RPAREN)
    return FunctionCall(name=name, args=args)
```
No existing parsing function changes.

### Variables (future)
Add a `_parse_statement` function above `_parse_expr`:
```python
def _parse_statement(self) -> ASTNode:
    if (self._current.type == TokenType.IDENT and
            self._peek().type == TokenType.EQUAL):
        ...  # assignment
    return self._parse_expr()
```
`parse()` calls `_parse_statement` instead of `_parse_expr` directly.

### New infix precedence level (future)
Insert a new `_parse_<level>` function in the call chain between the two adjacent levels.

---

## 8. Test Strategy

Tests live in `tests/test_parser.py`. The parser is tested by constructing a `Lexer` from an expression string and asserting on the returned AST structure.

### 8.1 Happy-Path Tests

| Expression | Expected AST |
|---|---|
| `"2"` | `Number(2.0)` |
| `"2 + 3"` | `BinaryOp('+', Number(2.0), Number(3.0))` |
| `"2 + 3 * 4"` | `BinaryOp('+', Number(2.0), BinaryOp('*', Number(3.0), Number(4.0)))` |
| `"(2 + 3) * 4"` | `BinaryOp('*', BinaryOp('+', Number(2.0), Number(3.0)), Number(4.0))` |
| `"-5"` | `UnaryOp('-', Number(5.0))` |
| `"--5"` | `UnaryOp('-', UnaryOp('-', Number(5.0)))` |
| `"2 - -3"` | `BinaryOp('-', Number(2.0), UnaryOp('-', Number(3.0)))` |

### 8.2 Error-Path Tests

```python
import pytest
from calc.errors import UnexpectedEnd, UnexpectedToken
from calc.lexer import Lexer
from calc.parser import Parser

@pytest.mark.parametrize("expr,error_type", [
    ("2 +",    UnexpectedEnd),
    ("(2 + 3", UnexpectedEnd),
    ("2 3",    UnexpectedToken),
    ("2 + )",  UnexpectedToken),
    ("(2 + 3 4", UnexpectedToken),
])
def test_parse_errors(expr, error_type):
    with pytest.raises(error_type):
        Parser(Lexer(expr)).parse()
```

### 8.3 Precedence and Associativity

Precedence is verified via AST structure, not evaluated result, so a bug in the evaluator cannot mask a parser precedence bug:

```python
def test_precedence_mul_over_add():
    ast = Parser(Lexer("2 + 3 * 4")).parse()
    assert ast == BinaryOp('+', Number(2.0), BinaryOp('*', Number(3.0), Number(4.0)))

def test_left_associativity():
    ast = Parser(Lexer("2 - 3 - 4")).parse()
    assert ast == BinaryOp('-', BinaryOp('-', Number(2.0), Number(3.0)), Number(4.0))
```

### 8.4 Coverage Target

All five grammar rules (`_parse_expr`, `_parse_term`, `_parse_factor`, `_parse_unary`, `_parse_primary`) and both error-raising paths in `_expect` must be exercised. The parametrized error tests above achieve this with no redundancy.

---

## 9. Dependencies

| Dependency | Direction | Notes |
|---|---|---|
| `src/calc/lexer.py` | imports `Lexer`, `Token`, `TokenType` | parser calls `lexer.next_token()` |
| `src/calc/errors.py` | imports `UnexpectedToken`, `UnexpectedEnd` | parser raises these |
| `src/calc/evaluator.py` | imports `ASTNode` types | evaluator imports from `parser.py` (one-way) |

The parser module has no circular imports. `errors.py` has no dependencies; `lexer.py` has no dependencies; `parser.py` depends on both.
