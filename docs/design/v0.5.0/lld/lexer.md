# Low-Level Design — Lexer Module (v0.5.0)

**Module:** `lexer`
**File:** `src/calc/lexer.py`
**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

Convert a raw source string into a flat, on-demand token stream. The lexer is a
*lazy/pull* lexer: it produces one token per call to `next_token()` and maintains no
intermediate token list. The parser drives all consumption.

The lexer is unchanged in v0.5.0. No new token types, keywords, or lexical rules are
introduced. This document records the complete design so that the implementation can be
verified against it during code review.

---

## 2. Data Structures

### 2.1 `TokenType` (enum)

```python
class TokenType(Enum):
    NUMBER    = auto()   # integer or floating-point literal
    PLUS      = auto()   # +
    MINUS     = auto()   # -
    STAR      = auto()   # *
    SLASH     = auto()   # /
    LPAREN    = auto()   # (
    RPAREN    = auto()   # )
    COMMA     = auto()   # ,
    SEMICOLON = auto()   # ;
    EQUALS    = auto()   # =
    EOF       = auto()   # end of input
    UNKNOWN   = auto()   # any character not matched by the rules above
    IDENT     = auto()   # identifier (not a keyword)
    DEF       = auto()   # reserved keyword "def"
```

14 members total. `auto()` assigns sequential integer values; the exact integers are
an implementation detail and must not be relied upon outside this module.

### 2.2 `Token` (frozen dataclass)

```python
@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str          # raw lexeme; "" for EOF
```

- Immutable: `frozen=True` prevents accidental mutation after construction.
- `value` always contains the exact source characters that produced the token.
  - For `EOF`: `value == ""`
  - For single-character tokens: `value` is that one character (e.g. `"+"`)
  - For `NUMBER`: full numeric lexeme (e.g. `"3.14"`, `"1e-6"`, `".5"`)
  - For `IDENT`/`DEF`: the identifier text (e.g. `"sin"`, `"def"`)
  - For `UNKNOWN`: the unrecognised character

### 2.3 Module-level lookup tables

```python
_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUALS,
}

_KEYWORDS: dict[str, TokenType] = {
    "def": TokenType.DEF,
}
```

Both tables are module-level constants. `_SINGLE_CHAR` enables O(1) dispatch for
all single-character operators. `_KEYWORDS` is consulted after a full identifier has
been scanned; unrecognised identifiers fall through to `TokenType.IDENT`.

---

## 3. `Lexer` Class

### 3.1 Constructor

```python
class Lexer:
    def __init__(self, input: str) -> None:
        self._input: str = input
        self._cursor: int = 0
```

- `_input` — the complete source string; never mutated.
- `_cursor` — index of the next character to be examined; starts at 0.

### 3.2 Public Interface

| Method | Signature | Description |
|--------|-----------|-------------|
| `next_token` | `() → Token` | Advance past whitespace, then scan and return the next token. Returns `Token(EOF, "")` when the input is exhausted; continues to return `EOF` on every subsequent call. |

### 3.3 Private Helpers

| Method | Signature | Description |
|--------|-----------|-------------|
| `_peek` | `() → str` | Return `_input[_cursor]` without advancing; return `""` when cursor is past the end. |
| `_advance` | `() → str` | Return `_peek()`, then increment `_cursor` by 1. |
| `_skip_whitespace` | `() → None` | Advance past space (`" "`) and tab (`"\t"`) characters. |
| `_scan_number` | `() → Token` | Scan a numeric literal; see §4.1. |
| `_scan_ident` | `() → Token` | Scan an identifier or keyword; see §4.2. |

---

## 4. Key Algorithms

### 4.1 `next_token` dispatch

```
next_token():
  _skip_whitespace()
  if cursor >= len(input):
      return Token(EOF, "")
  ch = _peek()
  if ch in _SINGLE_CHAR:
      _advance()
      return Token(_SINGLE_CHAR[ch], ch)
  if ch.isdigit() or ch == ".":
      return _scan_number()
  if ch.isalpha() or ch == "_":
      return _scan_ident()
  _advance()
  return Token(UNKNOWN, ch)
```

Priority order (highest to lowest):

1. Whitespace skip (no token produced)
2. End-of-input → `EOF`
3. Single-character operator → corresponding `TokenType`
4. Digit or `.` → `_scan_number`
5. Letter or `_` → `_scan_ident`
6. Anything else → `UNKNOWN`

### 4.2 `_scan_number` — numeric literal recognition

Recognised number formats:

| Pattern | Example | Notes |
|---------|---------|-------|
| Integer | `42` | |
| Float | `3.14` | |
| Leading-dot float | `.5` | |
| Trailing-dot float | `3.` | |
| Scientific (lower `e`) | `1e6`, `1e+6`, `1e-6` | |
| Scientific (upper `E`) | `2.5E-3` | |

Algorithm (pseudocode):

```
_scan_number():
  start = cursor
  if peek() == ".":
      advance()                         # leading-dot case
      while peek().isdigit(): advance()
  else:
      while peek().isdigit(): advance() # integer part
      if peek() == ".":
          advance()                     # decimal point
          while peek().isdigit(): advance()
  # optional exponent with speculative rollback
  if peek() in ("e", "E"):
      saved = cursor
      advance()                         # tentatively consume e/E
      if peek() in ("+", "-"):
          advance()                     # optional sign
      if peek().isdigit():
          while peek().isdigit(): advance()
          # exponent is valid; cursor stays advanced
      else:
          cursor = saved                # rollback: leave "e"/"E" for identifier scanner
  return Token(NUMBER, input[start:cursor])
```

**Rollback rule:** if `e`/`E` is not followed by an optional sign and at least one
digit, the cursor is restored to the position before `e`/`E`. This allows `3ex` to
tokenise as `NUMBER("3")` + `IDENT("ex")` rather than `UNKNOWN` or an error.

### 4.3 `_scan_ident` — identifier and keyword recognition

```
_scan_ident():
  start = cursor
  while peek().isalnum() or peek() == "_":
      advance()
  text = input[start:cursor]
  return Token(_KEYWORDS.get(text, IDENT), text)
```

- Identifier start characters: `[A-Za-z_]` (checked by caller via `ch.isalpha() or ch == "_"`)
- Identifier continuation characters: `[A-Za-z0-9_]` (`.isalnum() or == "_"`)
- Keyword lookup: if `text` is in `_KEYWORDS`, the corresponding `TokenType` is used
  (currently only `"def"` → `DEF`); otherwise `IDENT`.

---

## 5. Public API / Interfaces

The public surface of this module is:

```python
# Types
class TokenType(Enum): ...          # 14 members
class Token: ...                    # frozen dataclass: type, value

# Constants (package-internal; not re-exported by __init__.py)
_KEYWORDS: dict[str, TokenType]     # keyword dispatch table

# Class
class Lexer:
    def __init__(self, source: str) -> None: ...
    def next_token(self) -> Token: ...
```

`_SINGLE_CHAR` and `_KEYWORDS` use the `_` prefix to signal package-internal use.
The parser imports `Lexer`, `Token`, and `TokenType` directly from `calc.lexer`.

**No changes to this API are made in v0.5.0.** Both the legacy expression path and
the plot path use the same `Lexer` class without modification.

---

## 6. Error Handling

The lexer **never raises a `CalcError`**. Unrecognised input characters are returned
as `Token(UNKNOWN, ch)`. The parser is responsible for detecting and raising
`UnexpectedToken` when it receives an `UNKNOWN` token in an invalid position.

This design keeps the lexer free of error-handling logic and simplifies testing:
every possible input character produces a well-defined token.

| Condition | Lexer behaviour | Who handles it |
|-----------|-----------------|----------------|
| Unrecognised character | Return `Token(UNKNOWN, ch)` | Parser raises `UnexpectedToken` |
| End of input | Return `Token(EOF, "")` on every call | Parser raises `UnexpectedEnd` if more input expected |
| Malformed exponent (`3e+x`) | Rollback; return `Token(NUMBER, "3")` | Parser handles `IDENT("e")` as next token |
| Empty string input | Return `Token(EOF, "")` immediately | Parser raises `EmptyExpression` |

---

## 7. Test Strategy

### 7.1 Scope

`tests/test_lexer.py` (existing file). No new test cases are added in v0.5.0 because
no new tokens or lexical rules are introduced. The table below documents what the
existing tests must cover for completeness.

### 7.2 Test cases

#### Single-character tokens

| Input | Expected token sequence |
|-------|------------------------|
| `"+"` | `PLUS("+")`, `EOF` |
| `"-"` | `MINUS("-")`, `EOF` |
| `"*"` | `STAR("*")`, `EOF` |
| `"/"` | `SLASH("/")`, `EOF` |
| `"("` | `LPAREN("(")`, `EOF` |
| `")"` | `RPAREN(")")`, `EOF` |
| `","` | `COMMA(",")`, `EOF` |
| `";"` | `SEMICOLON(";")`, `EOF` |
| `"="` | `EQUALS("=")`, `EOF` |

#### Numeric literals

| Input | Expected `value` |
|-------|-----------------|
| `"0"` | `"0"` |
| `"42"` | `"42"` |
| `"3.14"` | `"3.14"` |
| `".5"` | `".5"` |
| `"3."` | `"3."` |
| `"1e6"` | `"1e6"` |
| `"1E6"` | `"1E6"` |
| `"1e+6"` | `"1e+6"` |
| `"1e-6"` | `"1e-6"` |
| `"2.5E-3"` | `"2.5E-3"` |
| `"3ex"` | `NUMBER("3")`, `IDENT("ex")`, `EOF` (rollback case) |

#### Identifiers and keywords

| Input | Expected token |
|-------|----------------|
| `"x"` | `IDENT("x")` |
| `"sin"` | `IDENT("sin")` |
| `"_foo"` | `IDENT("_foo")` |
| `"foo123"` | `IDENT("foo123")` |
| `"def"` | `DEF("def")` |
| `"define"` | `IDENT("define")` (not a keyword) |

#### Whitespace handling

| Input | Expected token sequence |
|-------|------------------------|
| `"  3"` | `NUMBER("3")`, `EOF` |
| `"\t3"` | `NUMBER("3")`, `EOF` |
| `"3 + 4"` | `NUMBER("3")`, `PLUS("+")`, `NUMBER("4")`, `EOF` |

#### Unknown characters

| Input | Expected token |
|-------|----------------|
| `"@"` | `UNKNOWN("@")` |
| `"#"` | `UNKNOWN("#")` |

#### EOF idempotence

- After input is exhausted, every subsequent call to `next_token()` returns
  `Token(EOF, "")`.

#### Compound expression

| Input | Expected token sequence |
|-------|------------------------|
| `"def f(x) = x + 1"` | `DEF`, `IDENT("f")`, `LPAREN`, `IDENT("x")`, `RPAREN`, `EQUALS`, `IDENT("x")`, `PLUS`, `NUMBER("1")`, `EOF` |

### 7.3 Test implementation pattern

```python
def tokenise(source: str) -> list[Token]:
    lex = Lexer(source)
    tokens = []
    while True:
        tok = lex.next_token()
        tokens.append(tok)
        if tok.type == TokenType.EOF:
            break
    return tokens
```

Tests call `tokenise()` and assert on the resulting list using standard `assert`
statements or `pytest` parametrise decorators. No mocking is required; the lexer has
no external dependencies.

---

## 8. Implementation Notes

- **No import beyond stdlib `dataclasses` and `enum`.** The lexer has zero
  dependencies on other `calc` modules.
- **`from __future__ import annotations`** is present for forward-reference
  compatibility; no runtime behaviour change.
- **No `\n` or `\r` in whitespace skip.** Only space and tab are skipped; newlines
  produce `UNKNOWN` tokens. This is intentional: the input format for this tool is a
  single-line expression. If multi-line support is added in future, `_skip_whitespace`
  is the only site to change.
- **`_KEYWORDS` is designed for extension.** Adding a new keyword in a future version
  requires only one dict entry and one new `TokenType` member; no change to
  `_scan_ident` is needed.
- **Cursor state is mutable only inside `Lexer`.** The `_cursor` integer is never
  exposed; callers cannot advance or reset the lexer externally.
