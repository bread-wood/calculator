# Low-Level Design — Lexer Module (v0.1.0)

**Milestone:** v0.1.0
**Module:** `lexer`
**File:** `src/calc/lexer.py`
**Date:** 2026-03-04
**Status:** Draft

---

## 1. Responsibilities

The lexer converts a raw expression string into a pull-model stream of typed tokens. It has no dependency on any other `calc` module. It does not evaluate or parse — it only identifies and classifies characters.

---

## 2. Data Structures

### 2.1 `TokenType` Enum

```python
from enum import Enum, auto

class TokenType(Enum):
    NUMBER  = auto()
    PLUS    = auto()
    MINUS   = auto()
    STAR    = auto()
    SLASH   = auto()
    LPAREN  = auto()
    RPAREN  = auto()
    EOF     = auto()
    UNKNOWN = auto()
```

Nine variants cover all v0.1.0 token classes. `UNKNOWN` carries the offending character so the parser can include it in context if needed.

### 2.2 `Token` Dataclass

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str          # raw lexeme; "" for EOF
```

`frozen=True` prevents accidental mutation. `value` holds the exact substring consumed from the input (e.g., `"3.14"` for a NUMBER, `"@"` for UNKNOWN, `""` for EOF).

### 2.3 `Lexer` Class (Scanner)

```python
class Lexer:
    _input:  str
    _cursor: int        # index of the next character to consume
```

`_input` and `_cursor` are private. No other state is required. The parser holds the `Lexer` instance and calls `next_token()` on demand.

---

## 3. Public API

```python
class Lexer:
    def __init__(self, input: str) -> None: ...
    def next_token(self) -> Token: ...
```

| Method | Description |
|---|---|
| `__init__(input)` | Stores the expression string; sets `_cursor = 0`. |
| `next_token()` | Returns the next `Token`. Caller may call repeatedly until `Token(EOF, "")` is returned. After EOF, every subsequent call also returns EOF. |

The parser is the only caller of `next_token()`. No iterator protocol (`__iter__` / `__next__`) is exposed; the pull model is explicit.

---

## 4. Key Algorithms

### 4.1 `next_token()` Dispatch

```
next_token():
    skip whitespace (space, tab)
    if cursor >= len(input):
        return Token(EOF, "")
    ch = peek()
    if ch in ('+', '-', '*', '/', '(', ')'):
        advance
        return Token(<matching type>, ch)
    if ch.isdigit() or ch == '.':
        return scan_number()
    advance
    return Token(UNKNOWN, ch)
```

Whitespace is consumed silently. All branches advance the cursor at most once before delegating or returning — no look-ahead beyond `peek()`.

### 4.2 `peek()` and `advance()`

```python
def _peek(self) -> str:
    if self._cursor < len(self._input):
        return self._input[self._cursor]
    return ""          # sentinel for end-of-input

def _advance(self) -> str:
    ch = self._peek()
    self._cursor += 1
    return ch
```

Private helpers. `_peek()` returns `""` at end-of-input, which is distinct from any valid character and acts as a natural sentinel.

### 4.3 `scan_number()`

Handles integers, floats, leading-dot, and trailing-dot forms.

```
scan_number():
    start = cursor
    if peek() == '.':
        advance                 # leading dot (.5)
        consume digits
    else:
        consume digits          # integer part
        if peek() == '.':
            advance             # decimal point
            consume digits      # fractional part (may be zero — trailing dot: 3.)
    return Token(NUMBER, input[start:cursor])
```

**Edge-case table:**

| Input | Lexeme produced | Notes |
|-------|-----------------|-------|
| `3`   | `"3"`           | Integer |
| `3.14`| `"3.14"`        | Standard float |
| `.5`  | `".5"`          | Leading dot — accepted |
| `3.`  | `"3."`          | Trailing dot — accepted |
| `..`  | `"."` then `UNKNOWN('.')` | First `.` starts scan; no digits follow; second `.` is UNKNOWN |

`float(".5")` and `float("3.")` are valid Python built-ins, so the raw lexeme is safe to pass directly to `float()` during evaluation.

### 4.4 Whitespace Skipping

```python
def _skip_whitespace(self) -> None:
    while self._peek() in (' ', '\t'):
        self._advance()
```

Only space and tab are skipped. No newline handling is required (single-line expressions).

---

## 5. Error Handling

The lexer does **not** raise exceptions. Instead, it emits `Token(UNKNOWN, ch)` for any character it cannot classify. Rationale:

- Keeps the lexer's contract uniform: `next_token()` always returns a `Token`.
- Allows the parser to accumulate the offending character for error context.
- Simplifies unit testing: test code never needs to catch exceptions from the lexer.

The parser, upon receiving a `Token(UNKNOWN, ...)`, raises `UnexpectedToken` from `errors.py`. The error message `"error: unexpected token"` is defined in `errors.py`; the lexer never writes to stderr.

**Dependency:** `lexer.py` imports only from `errors.py` (for `UnexpectedToken`) — actually, it does not even import `errors.py` since it emits the token rather than raising. `lexer.py` has **zero imports** from other `calc` modules.

---

## 6. Extensibility

Adding identifier tokens for function names / variables in a future version:

1. Add `IDENT = auto()` to `TokenType`.
2. Add one branch to `next_token()`:
   ```
   if ch.isalpha() or ch == '_':
       return scan_ident()
   ```
3. Implement `scan_ident()`:
   ```
   scan_ident():
       start = cursor
       while peek().isalnum() or peek() == '_':
           advance
       return Token(IDENT, input[start:cursor])
   ```
4. No other lexer code changes.

---

## 7. Module Boundary

| Concern | Owner |
|---|---|
| Tokenization | `lexer.py` |
| Token type definitions | `lexer.py` (`TokenType`, `Token`) |
| Error messages | `errors.py` |
| Raising `UnexpectedToken` on UNKNOWN | `parser.py` |
| stderr writes | `__main__.py` |

`lexer.py` imports nothing from other `calc` modules. It may import from the Python standard library only (currently none required beyond built-in string methods).

---

## 8. Test Strategy

**File:** `tests/test_lexer.py`

All tests instantiate `Lexer(input_string)` and call `next_token()` in a loop or individually. No parser, evaluator, or subprocess involvement.

### 8.1 Token-list parameterized tests

```python
import pytest
from calc.lexer import Lexer, Token, TokenType

@pytest.mark.parametrize("src, expected", [
    ("2 + 3",       [Token(TokenType.NUMBER, "2"),
                     Token(TokenType.PLUS, "+"),
                     Token(TokenType.NUMBER, "3"),
                     Token(TokenType.EOF, "")]),
    ("10 / 4",      [Token(TokenType.NUMBER, "10"),
                     Token(TokenType.SLASH, "/"),
                     Token(TokenType.NUMBER, "4"),
                     Token(TokenType.EOF, "")]),
    ("(2+3)*4",     [Token(TokenType.LPAREN, "("),
                     Token(TokenType.NUMBER, "2"),
                     Token(TokenType.PLUS, "+"),
                     Token(TokenType.NUMBER, "3"),
                     Token(TokenType.RPAREN, ")"),
                     Token(TokenType.STAR, "*"),
                     Token(TokenType.NUMBER, "4"),
                     Token(TokenType.EOF, "")]),
    ("-3",          [Token(TokenType.MINUS, "-"),
                     Token(TokenType.NUMBER, "3"),
                     Token(TokenType.EOF, "")]),
])
def test_token_list(src, expected):
    lex = Lexer(src)
    tokens = []
    while True:
        t = lex.next_token()
        tokens.append(t)
        if t.type == TokenType.EOF:
            break
    assert tokens == expected
```

### 8.2 Number literal edge cases

| Test case | Input | Expected token value |
|---|---|---|
| Integer | `"42"` | `NUMBER("42")` |
| Standard float | `"3.14"` | `NUMBER("3.14")` |
| Leading dot | `".5"` | `NUMBER(".5")` |
| Trailing dot | `"3."` | `NUMBER("3.")` |
| Multi-digit | `"100"` | `NUMBER("100")` |

### 8.3 Unknown character

```python
def test_unknown_character():
    lex = Lexer("@")
    t = lex.next_token()
    assert t.type == TokenType.UNKNOWN
    assert t.value == "@"

def test_unknown_then_eof():
    lex = Lexer("$")
    assert lex.next_token().type == TokenType.UNKNOWN
    assert lex.next_token().type == TokenType.EOF
```

### 8.4 Whitespace handling

```python
def test_whitespace_skipped():
    lex = Lexer("  2  +  3  ")
    assert lex.next_token() == Token(TokenType.NUMBER, "2")
    assert lex.next_token() == Token(TokenType.PLUS, "+")
    assert lex.next_token() == Token(TokenType.NUMBER, "3")
    assert lex.next_token() == Token(TokenType.EOF, "")
```

### 8.5 EOF idempotency

```python
def test_eof_idempotent():
    lex = Lexer("")
    assert lex.next_token().type == TokenType.EOF
    assert lex.next_token().type == TokenType.EOF  # repeated calls safe
```

### 8.6 All single-character operators

```python
@pytest.mark.parametrize("ch, tt", [
    ("+", TokenType.PLUS),
    ("-", TokenType.MINUS),
    ("*", TokenType.STAR),
    ("/", TokenType.SLASH),
    ("(", TokenType.LPAREN),
    (")", TokenType.RPAREN),
])
def test_single_char_operators(ch, tt):
    t = Lexer(ch).next_token()
    assert t.type == tt
    assert t.value == ch
```

### 8.7 Coverage goal

100 % line coverage of `lexer.py` via the unit tests above. Integration coverage via `tests/test_cli.py` (spec criterion SC-9: `calc 'abc'` → `error: unexpected token`, exit 1).

---

## 9. Open Questions Resolved

| Question (from HLD) | Decision |
|---|---|
| Emit `UNKNOWN` or raise immediately? | **Emit `UNKNOWN` token.** Keeps lexer contract uniform; parser raises `UnexpectedToken`. |

No remaining open questions for the lexer module in v0.1.0.
