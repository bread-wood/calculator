# Low-Level Design — Lexer Module (v0.2.0)

**Milestone:** v0.2.0
**Module:** `lexer`
**File:** `src/calc/lexer.py`
**Date:** 2026-03-04
**Status:** Draft

---

## 1. Overview

### Responsibility

The lexer converts a raw expression string into a pull-model stream of typed `Token` objects. It scans characters left-to-right, classifying each group into the smallest meaningful unit (a token) without any semantic interpretation. It is the sole module responsible for character-level decisions: what constitutes a number, what constitutes an identifier, and which single characters are operators or separators.

v0.2.0 adds two new token types to support function calls (`sqrt(9)`) and named constants (`pi`, `e`):
- `IDENT` — a sequence of alphanumeric characters and underscores starting with a letter or underscore.
- `COMMA` — the `,` separator used between function arguments.

All other lexer behavior is unchanged from v0.1.0.

### What this module does NOT do

- It does not parse or validate expression structure (parser's responsibility).
- It does not evaluate or resolve identifiers to values (evaluator's responsibility).
- It does not raise exceptions — unrecognized characters produce `Token(UNKNOWN, ch)`.
- It does not distinguish function names from constant names; all alphabetic identifiers produce `IDENT`.
- It does not handle multi-line input or newlines (single-line contract, inherited from v0.1.0).

---

## 2. Public Interface

```python
class TokenType(Enum):
    NUMBER  = auto()
    PLUS    = auto()
    MINUS   = auto()
    STAR    = auto()
    SLASH   = auto()
    LPAREN  = auto()
    RPAREN  = auto()
    COMMA   = auto()   # NEW v0.2.0
    EOF     = auto()
    UNKNOWN = auto()
    IDENT   = auto()   # NEW v0.2.0

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

Eleven variants in v0.2.0 (up from nine in v0.1.0). Two additions:

| Variant | v0.1.0 | v0.2.0 | Notes |
|---------|--------|--------|-------|
| `NUMBER` | ✓ | ✓ | Numeric literals (int, float, sci-notation) |
| `PLUS` | ✓ | ✓ | `+` |
| `MINUS` | ✓ | ✓ | `-` |
| `STAR` | ✓ | ✓ | `*` |
| `SLASH` | ✓ | ✓ | `/` |
| `LPAREN` | ✓ | ✓ | `(` |
| `RPAREN` | ✓ | ✓ | `)` |
| `EOF` | ✓ | ✓ | End of input sentinel |
| `UNKNOWN` | ✓ | ✓ | Any unrecognised character |
| `COMMA` | — | ✓ | `,` argument separator |
| `IDENT` | — | ✓ | Alphabetic identifier |

### 3.2 `Token` Dataclass

```python
@dataclass(frozen=True)
class Token:
    type:  TokenType
    value: str   # raw lexeme; "" for EOF
```

`frozen=True` prevents accidental mutation. `value` holds the exact substring consumed: e.g., `"sqrt"` for `IDENT`, `","` for `COMMA`, `"1e10"` for `NUMBER`, `""` for `EOF`.

### 3.3 `Lexer` Internal State

```python
class Lexer:
    _input:  str   # the full expression string (immutable after __init__)
    _cursor: int   # index of the next character to examine
```

No other instance state. The parser holds the `Lexer` instance and calls `next_token()` on demand (pull model).

### 3.4 `_SINGLE_CHAR` dispatch table

```python
_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,   # NEW v0.2.0
}
```

Adding `COMMA` here requires zero changes to `next_token()`'s dispatch logic — the existing `if ch in _SINGLE_CHAR` branch handles it automatically. (Research #65)

---

## 4. Key Algorithms and Logic

### 4.1 `next_token()` Dispatch

```
next_token():
    skip_whitespace()
    if cursor >= len(input):
        return Token(EOF, "")
    ch = peek()
    if ch in _SINGLE_CHAR:
        advance()
        return Token(_SINGLE_CHAR[ch], ch)      # includes COMMA in v0.2.0
    if ch.isdigit() or ch == ".":
        return _scan_number()
    if ch.isalpha() or ch == "_":               # NEW v0.2.0
        return _scan_ident()
    advance()
    return Token(UNKNOWN, ch)
```

The `IDENT` branch is inserted **before** the `UNKNOWN` fallthrough and **after** the digit/dot check. This ordering is intentional:
- Digits and `.` are checked first so that numbers starting with a digit are never misrouted to `_scan_ident()`.
- Alphabetic characters can never start a number, so no conflict exists with `_scan_number()`.

### 4.2 `_scan_ident()` — Identifier scanning

```python
def _scan_ident(self) -> Token:
    start = self._cursor
    while self._peek().isalnum() or self._peek() == "_":
        self._advance()
    return Token(TokenType.IDENT, self._input[start:self._cursor])
```

- Entry condition: `peek()` is `isalpha()` or `"_"` (guaranteed by dispatch in `next_token()`).
- The first character is NOT consumed by `next_token()` before calling `_scan_ident()`; the scan starts fresh at `_cursor`.
- The body loop advances as long as the character is alphanumeric or `_`, capturing identifiers like `sqrt`, `atan2`, `log10` (hypothetical), and `_var`.
- Returns immediately when a non-alphanumeric, non-underscore character is seen (operator, space, EOF sentinel `""`).

**Examples:**

| Input fragment | Lexeme | Remaining |
|----------------|--------|-----------|
| `sqrt(` | `"sqrt"` | `(…` |
| `pi` | `"pi"` | EOF |
| `e` | `"e"` | EOF |
| `atan2` | `"atan2"` | EOF |

### 4.3 `_scan_number()` — Look-ahead guard for `e`/`E` (bug fix, #66)

The v0.1.x `_scan_number()` unconditionally consumed `e`/`E` after digits, producing malformed tokens like `NUMBER("2e")` when the expression is `2e` (user intending `2 * e`). Since v0.2.0 introduces `e` as a named constant, `2e` is a realistic mis-typed input; an uncaught `ValueError` from `float("2e")` in the parser is unacceptable.

**Fix:** add a look-ahead rollback when `e`/`E` is not followed by at least one digit (after optional sign):

```python
# v0.2.0 replacement for the exponent block in _scan_number():
if self._peek() in ("e", "E"):
    saved = self._cursor
    self._advance()                    # tentatively consume e/E
    if self._peek() in ("+", "-"):
        self._advance()
    if self._peek().isdigit():
        while self._peek().isdigit():
            self._advance()            # valid exponent: consume all digits
    else:
        self._cursor = saved           # rollback — leave e/E for IDENT branch
```

**Impact on valid scientific notation:** none. The guard fires only when no digit follows `e`/`E` (after optional sign). All valid exponent forms (`1e10`, `1e+10`, `2.5E-3`) satisfy the digit check immediately.

**Token stream for `2e`:** `NUMBER("2")` then `IDENT("e")`. The parser sees two consecutive primaries and raises `UnexpectedToken` → `error: unexpected token`. No `ValueError` reaches the user.

**Edge-case table (complete):**

| Input | Tokens produced | Notes |
|-------|-----------------|-------|
| `1e10` | `NUMBER("1e10")` | Valid sci-notation, unaffected |
| `1e+10` | `NUMBER("1e+10")` | Valid sci-notation, unaffected |
| `1e-5` | `NUMBER("1e-5")` | Valid sci-notation, unaffected |
| `1.5E2` | `NUMBER("1.5E2")` | Valid sci-notation, unaffected |
| `2e` | `NUMBER("2")`, `IDENT("e")` | Rollback; `e` dispatched as IDENT |
| `2e+` | `NUMBER("2")`, `IDENT("e")`, `PLUS("+")` | Rollback (no digit after sign) |
| `2e*3` | `NUMBER("2")`, `IDENT("e")`, `STAR("*")`, `NUMBER("3")` | Rollback (non-digit after e) |

### 4.4 Exponent ambiguity with `IDENT` dispatch (non-issue)

Research #53 confirmed: `_scan_number()` handles `e`/`E` **within** its own loop, after a digit has already been consumed. The IDENT branch in `next_token()` is only reached when `next_token()` freshly dispatches on a character — which means `_cursor` is pointing at an `e` that was **not** preceded by a digit in the same token. No ambiguity exists between the two branches.

### 4.5 `_peek()` and `_advance()` (unchanged)

```python
def _peek(self) -> str:
    if self._cursor < len(self._input):
        return self._input[self._cursor]
    return ""   # "" sentinel: distinct from any valid character

def _advance(self) -> str:
    ch = self._peek()
    self._cursor += 1
    return ch
```

`""` at EOF is a natural sentinel: `"".isalpha()`, `"".isdigit()`, and `"" in _SINGLE_CHAR` all return `False`, so every loop condition terminates cleanly at end-of-input.

### 4.6 `_skip_whitespace()` (unchanged)

```python
def _skip_whitespace(self) -> None:
    while self._peek() in (" ", "\t"):
        self._advance()
```

Space and tab only. No newline handling (single-line contract).

---

## 5. Internal Structure

### 5.1 File layout

`src/calc/lexer.py` contains, in order:

1. `from __future__ import annotations` (type annotation compatibility)
2. `from dataclasses import dataclass`
3. `from enum import Enum, auto`
4. `class TokenType(Enum)` — eleven variants
5. `@dataclass(frozen=True) class Token` — two fields
6. `_SINGLE_CHAR: dict[str, TokenType]` — seven entries (including `COMMA`)
7. `class Lexer` — `__init__`, `next_token`, `_peek`, `_advance`, `_skip_whitespace`, `_scan_number`, `_scan_ident`

No other top-level names are needed. No imports from other `calc` modules.

### 5.2 Private helpers summary

| Helper | Purpose |
|--------|---------|
| `_peek()` | Non-destructive look at the next character; returns `""` at EOF. |
| `_advance()` | Consumes and returns the next character; increments `_cursor`. |
| `_skip_whitespace()` | Skips spaces and tabs; called at the start of every `next_token()` call. |
| `_scan_number()` | Scans integer, float, and sci-notation literals; includes rollback guard for bare `e`/`E`. |
| `_scan_ident()` | Scans alphabetic identifiers (`sqrt`, `pi`, `e`, `atan2`, etc.). |

---

## 6. Error Handling

The lexer does **not** raise exceptions. Design rationale (carried over from v0.1.0):

- `next_token()` always returns a `Token` — the contract is uniform and callers never need to catch.
- Characters that cannot be classified produce `Token(UNKNOWN, ch)`, preserving the raw character for the parser's error message.
- The parser raises `UnexpectedToken` upon receiving an `UNKNOWN` token.

**What could go wrong and how it is handled:**

| Scenario | Lexer output | Who raises |
|----------|-------------|-----------|
| `@` in input | `Token(UNKNOWN, "@")` | Parser: `UnexpectedToken` |
| `$` in input | `Token(UNKNOWN, "$")` | Parser: `UnexpectedToken` |
| `2e` (malformed sci-notation) | `NUMBER("2")`, `IDENT("e")` | Parser: `UnexpectedToken` (two primaries in a row) |
| `""` (empty input) | `Token(EOF, "")` | `__main__`: `EmptyExpression` |

The lexer never catches or re-wraps any exception from its own code; there are no calls to external APIs that could raise.

---

## 7. Testing Strategy

**File:** `tests/test_lexer.py`

All tests instantiate `Lexer(input_string)` and call `next_token()` directly. No parser, evaluator, or subprocess involvement.

### 7.1 Existing tests (all must remain green)

| Test | What it covers |
|------|---------------|
| `test_token_list` (parametrized) | Full token sequences for arithmetic expressions |
| `test_number_literals` (parametrized) | INTEGER, FLOAT, leading-dot, trailing-dot forms |
| `test_single_char_operators` (parametrized) | All six v0.1.0 single-char tokens |
| `test_unknown_character` | `@` → `UNKNOWN` |
| `test_unknown_then_eof` | `$` → `UNKNOWN`, then `EOF` |
| `test_whitespace_skipped` | Spaces around tokens |
| `test_eof_idempotent` | Repeated `next_token()` after EOF |

None of these tests use `,` or alphabetic input; adding `COMMA` and `IDENT` does not affect them. (Research #53, #65)

### 7.2 New tests required (v0.2.0)

#### IDENT tokens

```python
@pytest.mark.parametrize("src, expected_value", [
    ("sqrt",   "sqrt"),
    ("pi",     "pi"),
    ("e",      "e"),
    ("atan2",  "atan2"),
    ("_var",   "_var"),
    ("x1",     "x1"),
])
def test_ident_token(src, expected_value):
    t = Lexer(src).next_token()
    assert t.type == TokenType.IDENT
    assert t.value == expected_value
```

#### COMMA token

```python
def test_comma_token():
    t = Lexer(",").next_token()
    assert t == Token(TokenType.COMMA, ",")

def test_comma_in_sequence():
    tokens = tokenize("2,3")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.COMMA, ","),
        Token(TokenType.NUMBER, "3"),
        Token(TokenType.EOF, ""),
    ]
```

#### COMMA added to single-char parametrize

Extend `test_single_char_operators` with `(",", TokenType.COMMA)`.

#### Scientific notation regression guard

```python
@pytest.mark.parametrize("src, expected_value", [
    ("1e10",   "1e10"),
    ("1e+10",  "1e+10"),
    ("1e-5",   "1e-5"),
    ("1.5E2",  "1.5E2"),
])
def test_sci_notation_unchanged(src, expected_value):
    t = Lexer(src).next_token()
    assert t.type == TokenType.NUMBER
    assert t.value == expected_value
```

#### `2e` rollback (bug fix #66)

```python
def test_bare_e_after_number():
    """2e must not produce a malformed NUMBER("2e") token."""
    tokens = tokenize("2e")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.IDENT, "e"),
        Token(TokenType.EOF, ""),
    ]

def test_2e_plus_produces_rollback():
    tokens = tokenize("2e+")
    assert tokens[0] == Token(TokenType.NUMBER, "2")
    assert tokens[1] == Token(TokenType.IDENT, "e")
    assert tokens[2] == Token(TokenType.PLUS, "+")

def test_2e_star_produces_rollback():
    tokens = tokenize("2e*3")
    assert tokens[0] == Token(TokenType.NUMBER, "2")
    assert tokens[1] == Token(TokenType.IDENT, "e")
```

#### IDENT in expression sequence

```python
def test_function_call_token_sequence():
    tokens = tokenize("sqrt(9)")
    assert tokens == [
        Token(TokenType.IDENT,  "sqrt"),
        Token(TokenType.LPAREN, "("),
        Token(TokenType.NUMBER, "9"),
        Token(TokenType.RPAREN, ")"),
        Token(TokenType.EOF,    ""),
    ]

def test_constant_in_expression():
    tokens = tokenize("2*pi")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.STAR,   "*"),
        Token(TokenType.IDENT,  "pi"),
        Token(TokenType.EOF,    ""),
    ]
```

### 7.3 What to mock

Nothing. The lexer operates on an in-memory string; there are no I/O boundaries, external calls, or non-deterministic behaviour to isolate.

### 7.4 Coverage goal

100% line coverage of `lexer.py` via the unit tests above. Integration coverage via `tests/test_cli.py` for the full pipeline (`sqrt(9)` → `3`, `pi` → `3.141592653589793`).

---

## 8. Dependencies

| Dependency | Source | Reason |
|------------|--------|--------|
| `dataclasses.dataclass` | Python stdlib | `Token` dataclass definition |
| `enum.Enum`, `enum.auto` | Python stdlib | `TokenType` enum definition |

**Zero imports from other `calc` modules.** `lexer.py` is the lowest layer of the dependency graph. This is intentional and must be preserved.

---

## 9. Open Questions Resolved

| HLD open question | Decision |
|-------------------|----------|
| Single `IDENT` type vs keyword tokens | **Single `IDENT`.** The lexer stays context-free; constants and functions are distinguished by the parser based on whether `LPAREN` follows. (Research #53, #43) |
| `COMMA` as first-class `TokenType` vs `UNKNOWN` fallthrough | **First-class `COMMA`.** Consistent with all other syntactically meaningful single-char tokens; avoids hidden parser-lexer coupling via value strings. (Research #65) |
| `2e` producing malformed `NUMBER` token | **Look-ahead rollback in `_scan_number`.** Fixes the lexer contract at the source; `e` surfaces correctly as `IDENT` for the evaluator constant lookup. (Research #66) |
