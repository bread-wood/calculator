# Low-Level Design — Lexer Module (v0.3.0)

**Milestone:** v0.3.0
**Module:** `lexer`
**File:** `src/calc/lexer.py`
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Overview

### Responsibility

The lexer converts a raw source string into a pull-model stream of typed `Token` objects. It scans characters left-to-right, classifying each group into the smallest meaningful unit without any semantic interpretation. It is the sole module responsible for character-level decisions.

v0.3.0 adds two new token types to support variable assignment (`x = 5`) and multi-statement programs (`x = 5; y = x * 2; y + 1`):
- `EQUALS` — the `=` assignment operator.
- `SEMICOLON` — the `;` statement separator.

Both are single-character tokens added to the existing `_SINGLE_CHAR` dispatch table. No other lexer logic changes. All v0.2.0 behaviour is preserved unchanged.

### What this module does NOT do

- It does not parse or validate expression structure (parser's responsibility).
- It does not evaluate or resolve identifiers to values (evaluator's responsibility).
- It does not raise exceptions — unrecognised characters produce `Token(UNKNOWN, ch)`.
- It does not distinguish assignment `=` from equality comparison; `EQUALS` is the only `=`-related token.
- It does not handle multi-line input or newlines (single-line contract, inherited from v0.1.0).

---

## 2. Public Interface

```python
class TokenType(Enum):
    NUMBER    = auto()
    PLUS      = auto()
    MINUS     = auto()
    STAR      = auto()
    SLASH     = auto()
    LPAREN    = auto()
    RPAREN    = auto()
    COMMA     = auto()
    EOF       = auto()
    UNKNOWN   = auto()
    IDENT     = auto()
    SEMICOLON = auto()   # NEW v0.3.0
    EQUALS    = auto()   # NEW v0.3.0

@dataclass(frozen=True)
class Token:
    type:  TokenType
    value: str          # raw lexeme; "" for EOF

class Lexer:
    def __init__(self, input: str) -> None: ...
    def next_token(self) -> Token: ...
```

| Symbol | Description |
|--------|-------------|
| `TokenType` | Enum of all token categories. |
| `Token` | Immutable dataclass; `value` holds the exact substring from the input. |
| `Lexer.__init__(input)` | Stores the expression string; initialises `_cursor = 0`. |
| `Lexer.next_token()` | Returns the next token. After EOF, every subsequent call also returns `Token(EOF, "")`. |

**Error types raised:** none. The lexer never raises exceptions.

---

## 3. Data Structures

### 3.1 `TokenType` Enum

Thirteen variants in v0.3.0 (up from eleven in v0.2.0). Two additions:

| Variant | v0.1.0 | v0.2.0 | v0.3.0 | Notes |
|---------|--------|--------|--------|-------|
| `NUMBER` | ✓ | ✓ | ✓ | Numeric literals (int, float, sci-notation) |
| `PLUS` | ✓ | ✓ | ✓ | `+` |
| `MINUS` | ✓ | ✓ | ✓ | `-` |
| `STAR` | ✓ | ✓ | ✓ | `*` |
| `SLASH` | ✓ | ✓ | ✓ | `/` |
| `LPAREN` | ✓ | ✓ | ✓ | `(` |
| `RPAREN` | ✓ | ✓ | ✓ | `)` |
| `EOF` | ✓ | ✓ | ✓ | End of input sentinel |
| `UNKNOWN` | ✓ | ✓ | ✓ | Any unrecognised character |
| `COMMA` | — | ✓ | ✓ | `,` argument separator |
| `IDENT` | — | ✓ | ✓ | Alphabetic identifier |
| `SEMICOLON` | — | — | ✓ | `;` statement separator |
| `EQUALS` | — | — | ✓ | `=` assignment operator |

### 3.2 `Token` Dataclass

Unchanged from v0.2.0:

```python
@dataclass(frozen=True)
class Token:
    type:  TokenType
    value: str   # raw lexeme; "" for EOF
```

`frozen=True` prevents accidental mutation. `value` holds the exact substring consumed: `";"` for `SEMICOLON`, `"="` for `EQUALS`, `""` for `EOF`.

### 3.3 `Lexer` Internal State

Unchanged from v0.2.0:

```python
class Lexer:
    _input:  str   # the full source string (immutable after __init__)
    _cursor: int   # index of the next character to examine
```

No other instance state.

### 3.4 `_SINGLE_CHAR` dispatch table

```python
_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,   # NEW v0.3.0
    "=": TokenType.EQUALS,      # NEW v0.3.0
}
```

Adding `SEMICOLON` and `EQUALS` here requires zero changes to `next_token()`'s dispatch logic — the existing `if ch in _SINGLE_CHAR` branch handles them automatically. (HLD decision: "Token additions — `SEMICOLON`, `EQUALS` in `_SINGLE_CHAR`", research #112.)

---

## 4. Key Algorithms and Logic

### 4.1 `next_token()` Dispatch

Unchanged from v0.2.0. `SEMICOLON` and `EQUALS` are handled transparently by the `_SINGLE_CHAR` table lookup:

```
next_token():
    skip_whitespace()
    if cursor >= len(input):
        return Token(EOF, "")
    ch = peek()
    if ch in _SINGLE_CHAR:
        advance()
        return Token(_SINGLE_CHAR[ch], ch)   # now includes SEMICOLON and EQUALS
    if ch.isdigit() or ch == ".":
        return _scan_number()
    if ch.isalpha() or ch == "_":
        return _scan_ident()
    advance()
    return Token(UNKNOWN, ch)
```

There is no ambiguity between `=` and any other token: `==` is not valid syntax in this language, and `=` is consumed one character at a time. Two adjacent `=` characters (`==`) produce `EQUALS, EQUALS` — the parser will raise `UnexpectedToken` at the second `=`.

### 4.2 `SEMICOLON` and `EQUALS` token examples

| Input fragment | Tokens produced |
|----------------|-----------------|
| `x = 5` | `IDENT("x")`, `EQUALS("=")`, `NUMBER("5")` |
| `x = 5; y = 2` | `IDENT("x")`, `EQUALS("=")`, `NUMBER("5")`, `SEMICOLON(";")`, `IDENT("y")`, `EQUALS("=")`, `NUMBER("2")` |
| `x = 5;` | `IDENT("x")`, `EQUALS("=")`, `NUMBER("5")`, `SEMICOLON(";")` |
| `pi = 3` | `IDENT("pi")`, `EQUALS("=")`, `NUMBER("3")` (parser/evaluator handle the constant error) |

### 4.3 All other algorithms (unchanged)

The following lexer methods are identical to v0.2.0 and are documented in full in the v0.2.0 LLD. They are summarised here for reference only:

| Method | Notes |
|--------|-------|
| `_scan_ident()` | Scans `[a-zA-Z_][a-zA-Z0-9_]*`; unchanged. Variable names like `x`, `my_var`, `counter1` are valid `IDENT` tokens. |
| `_scan_number()` | Integer, float, sci-notation with `e`/`E` rollback guard; unchanged. |
| `_peek()` | Non-destructive look; returns `""` at EOF; unchanged. |
| `_advance()` | Consumes and returns next character; unchanged. |
| `_skip_whitespace()` | Skips spaces and tabs; unchanged. |

---

## 5. Internal Structure

### 5.1 File layout

`src/calc/lexer.py` contains, in order:

1. `from __future__ import annotations`
2. `from dataclasses import dataclass`
3. `from enum import Enum, auto`
4. `class TokenType(Enum)` — thirteen variants (eleven from v0.2.0 plus `SEMICOLON`, `EQUALS`)
5. `@dataclass(frozen=True) class Token` — two fields (unchanged)
6. `_SINGLE_CHAR: dict[str, TokenType]` — nine entries (seven from v0.2.0 plus `";"` and `"="`)
7. `class Lexer` — `__init__`, `next_token`, `_peek`, `_advance`, `_skip_whitespace`, `_scan_number`, `_scan_ident` (all unchanged)

No other top-level names are needed. No imports from other `calc` modules.

### 5.2 Private helpers summary

| Helper | Purpose | Changed? |
|--------|---------|---------|
| `_peek()` | Non-destructive look at next character; returns `""` at EOF. | No |
| `_advance()` | Consumes and returns next character; increments `_cursor`. | No |
| `_skip_whitespace()` | Skips spaces and tabs. | No |
| `_scan_number()` | Scans integer, float, sci-notation literals with rollback guard for bare `e`/`E`. | No |
| `_scan_ident()` | Scans alphabetic identifiers. | No |

---

## 6. Error Handling

The lexer does **not** raise exceptions. This contract is unchanged from v0.1.0/v0.2.0.

**What could go wrong and how it is handled:**

| Scenario | Lexer output | Who raises |
|----------|-------------|-----------|
| `@` in input | `Token(UNKNOWN, "@")` | Parser: `UnexpectedToken` |
| `$` in input | `Token(UNKNOWN, "$")` | Parser: `UnexpectedToken` |
| `2e` (malformed sci-notation) | `NUMBER("2")`, `IDENT("e")` | Parser: `UnexpectedToken` |
| `""` (empty input) | `Token(EOF, "")` | CLI: `EmptyExpression` |
| `==` (double equals) | `EQUALS("=")`, `EQUALS("=")` | Parser: `UnexpectedToken` on second `=` |
| `x == 5` | `IDENT("x")`, `EQUALS("=")`, `EQUALS("=")`, `NUMBER("5")` | Parser: `UnexpectedToken` |

---

## 7. Testing Strategy

**File:** `tests/test_lexer.py`

All tests instantiate `Lexer(input_string)` and call `next_token()` directly. No parser, evaluator, or subprocess involvement.

### 7.1 Existing tests (all must remain green)

All v0.2.0 tests are unaffected. The full set — `test_token_list`, `test_number_literals`, `test_single_char_operators`, `test_unknown_character`, `test_unknown_then_eof`, `test_whitespace_skipped`, `test_eof_idempotent`, `test_ident_token`, `test_comma_token`, `test_comma_in_sequence`, `test_sci_notation_unchanged`, `test_bare_e_after_number`, `test_2e_plus_produces_rollback`, `test_2e_star_produces_rollback`, `test_function_call_token_sequence`, `test_constant_in_expression` — must all pass without modification.

### 7.2 New tests required (v0.3.0)

#### SEMICOLON token

```python
def test_semicolon_token():
    t = Lexer(";").next_token()
    assert t == Token(TokenType.SEMICOLON, ";")
```

#### EQUALS token

```python
def test_equals_token():
    t = Lexer("=").next_token()
    assert t == Token(TokenType.EQUALS, "=")
```

#### SEMICOLON and EQUALS added to single-char parametrize

Extend `test_single_char_operators` with:
- `(";", TokenType.SEMICOLON)`
- `("=", TokenType.EQUALS)`

#### Assignment statement token sequence

```python
def test_assignment_token_sequence():
    tokens = tokenize("x = 5")
    assert tokens == [
        Token(TokenType.IDENT,   "x"),
        Token(TokenType.EQUALS,  "="),
        Token(TokenType.NUMBER,  "5"),
        Token(TokenType.EOF,     ""),
    ]
```

#### Multi-statement token sequence

```python
def test_multi_statement_token_sequence():
    tokens = tokenize("x = 5; y = 2")
    assert tokens == [
        Token(TokenType.IDENT,      "x"),
        Token(TokenType.EQUALS,     "="),
        Token(TokenType.NUMBER,     "5"),
        Token(TokenType.SEMICOLON,  ";"),
        Token(TokenType.IDENT,      "y"),
        Token(TokenType.EQUALS,     "="),
        Token(TokenType.NUMBER,     "2"),
        Token(TokenType.EOF,        ""),
    ]
```

#### Trailing semicolon

```python
def test_trailing_semicolon():
    tokens = tokenize("x = 5;")
    assert tokens[-2] == Token(TokenType.SEMICOLON, ";")
    assert tokens[-1] == Token(TokenType.EOF, "")
```

#### Variable reference in expression

```python
def test_variable_reference_in_expression():
    tokens = tokenize("x * 2")
    assert tokens == [
        Token(TokenType.IDENT,  "x"),
        Token(TokenType.STAR,   "*"),
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.EOF,    ""),
    ]
```

### 7.3 What to mock

Nothing. The lexer operates on an in-memory string; there are no I/O boundaries, external calls, or non-deterministic behaviour to isolate.

### 7.4 Coverage goal

100% line coverage of `lexer.py` via the unit tests above. The only code change is the two new entries in `_SINGLE_CHAR`; the new token tests exercise those entries directly.

---

## 8. Dependencies

| Dependency | Source | Reason |
|------------|--------|--------|
| `dataclasses.dataclass` | Python stdlib | `Token` dataclass definition |
| `enum.Enum`, `enum.auto` | Python stdlib | `TokenType` enum definition |

**Zero imports from other `calc` modules.** `lexer.py` is the lowest layer of the dependency graph. This is intentional and must be preserved.

---

## 9. Open Questions Resolved

There are no open questions for the lexer module deferred from the HLD. The HLD explicitly specifies the mechanism: `SEMICOLON` and `EQUALS` are added to `_SINGLE_CHAR` (HLD §Key design decisions, row "Token additions", research #112). No lookahead, rollback, or new scanning method is needed.
