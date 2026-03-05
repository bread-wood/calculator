# Low-Level Design — Lexer Module (v0.4.0)

**Module:** `lexer` (`src/calc/lexer.py`)
**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Approved
**Issue:** #189
**Depends on:** HLD v0.4.0, Research #153, Research #158

---

## 1. Responsibility

The lexer converts a raw source string into a flat, pull-based token stream. The parser drives the stream by calling `next_token()` on demand; no intermediate token list is allocated. In v0.4.0 the sole new responsibility is recognising `def` as a reserved keyword and emitting `TokenType.DEF` instead of `TokenType.IDENT` when the lexeme is exactly `"def"`.

---

## 2. Data Structures

### 2.1 `TokenType` (enum)

```python
class TokenType(Enum):
    NUMBER    = auto()   # numeric literal
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
    UNKNOWN   = auto()   # unrecognised character
    IDENT     = auto()   # identifier (variable, constant, function name)
    DEF       = auto()   # reserved keyword 'def'  ← NEW in v0.4.0
```

Total: 14 variants. `DEF` is the only addition in v0.4.0.

### 2.2 `Token` (frozen dataclass)

```python
@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str   # raw lexeme; "" for EOF
```

Frozen so tokens are safely hashable and shareable. No change from v0.3.x.

### 2.3 `_SINGLE_CHAR` (module-level dict)

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
```

Lookup table for all syntactically meaningful single-character tokens. No change from v0.3.x.

### 2.4 `_KEYWORDS` (module-level dict) — NEW

```python
_KEYWORDS: dict[str, TokenType] = {
    "def": TokenType.DEF,
}
```

Maps reserved keyword strings to their `TokenType`. Placed at module level (not as a class attribute) so it is visible to `_scan_ident` without any `self.` indirection and so future keywords require only a one-line addition here with no other file changes.

### 2.5 `Lexer` (class)

Internal state:

| Attribute    | Type  | Purpose                                   |
|--------------|-------|-------------------------------------------|
| `_input`     | `str` | The full source string, immutable         |
| `_cursor`    | `int` | Current read position (0-indexed)         |

The cursor is the sole mutable state. The lexer is not rewindable; consumers must buffer tokens themselves if look-ahead is needed (the parser's `_lookahead` slot handles this).

---

## 3. Key Algorithms

### 3.1 `next_token()` — top-level dispatch

```
skip whitespace
if cursor >= len(input): return Token(EOF, "")
ch = peek()
if ch in _SINGLE_CHAR:    advance(); return Token(_SINGLE_CHAR[ch], ch)
if ch.isdigit() or ch == '.': return _scan_number()
if ch.isalpha() or ch == '_': return _scan_ident()
advance(); return Token(UNKNOWN, ch)
```

No change from v0.3.x except that `_scan_ident` now performs keyword lookup before returning.

### 3.2 `_scan_ident()` — with keyword lookup (CHANGED)

```python
def _scan_ident(self) -> Token:
    start = self._cursor
    while self._peek().isalnum() or self._peek() == "_":
        self._advance()
    text = self._input[start:self._cursor]
    tt = _KEYWORDS.get(text, TokenType.IDENT)
    return Token(tt, text)
```

The only change from v0.3.x is the `_KEYWORDS.get(text, TokenType.IDENT)` lookup. The match is exact (full lexeme equality), so:

- `"def"` → `Token(DEF, "def")`
- `"define"`, `"default"`, `"defun"` → `Token(IDENT, <text>)` (not in keyword table)
- All other identifiers → `Token(IDENT, <text>)` (unchanged)

### 3.3 `_scan_number()` — numeric scanning (unchanged)

Handles integer, decimal, and scientific notation (`e`/`E` with optional sign):

1. Scan leading digits (or leading `.`).
2. If a `.` follows digits, scan the fractional part.
3. If `e`/`E` follows, tentatively advance and check for an optional sign then at least one digit. If no digit follows, **roll back** the cursor to before `e`/`E` so that `e` is emitted as `IDENT` by the next `next_token()` call.

The rollback guard (`saved = self._cursor` / `self._cursor = saved`) is the mechanism that makes `2e` tokenise as `NUMBER("2") IDENT("e")` rather than as an invalid token.

No change in v0.4.0.

### 3.4 Whitespace skipping

`_skip_whitespace()` advances past `" "` and `"\t"` only. Newlines are not part of the input grammar (the CLI passes a single shell argument).

---

## 4. Public API / Interfaces

### Exports consumed by `parser.py`

| Name           | Kind            | Description                              |
|----------------|-----------------|------------------------------------------|
| `TokenType`    | `Enum`          | 14-variant type enumeration              |
| `Token`        | frozen dataclass | `(type: TokenType, value: str)`         |
| `Lexer`        | class           | `Lexer(source: str)`; pull interface     |
| `Lexer.next_token` | method     | Returns next `Token`; EOF is idempotent  |

`_SINGLE_CHAR` and `_KEYWORDS` are module-level but prefixed with `_` — not part of the public API.

### Constructor

```python
Lexer(input: str) -> Lexer
```

Creates a lexer over `input`. `input` is stored as-is; no preprocessing or normalisation.

### `next_token() → Token`

- Returns the next token from the stream.
- Calling after `EOF` returns another `EOF` (idempotent — confirmed by existing test `test_eof_idempotent`).
- Never raises; unrecognised characters produce `Token(UNKNOWN, ch)`.

---

## 5. Error Handling

The lexer does **not** raise exceptions. All error reporting is deferred to the parser:

- Unrecognised characters produce `Token(UNKNOWN, ch)`. The parser raises `UnexpectedToken` when it encounters an `UNKNOWN` token in a position where a valid token is required.
- Malformed numeric literals (e.g. `1.2.3`) are not explicitly rejected; the lexer produces the longest valid numeric prefix and leaves the remainder for subsequent `next_token()` calls. The parser will raise `UnexpectedToken` if the resulting token stream does not match any grammar rule.
- `def` followed by a non-identifier (e.g. `def 5(x) = x`) emits `Token(DEF, "def")` then `Token(NUMBER, "5")`; the parser's `_parse_funcdef` raises `UnexpectedToken` when it calls `_expect(TokenType.IDENT)` and sees `NUMBER` instead.

This design keeps the lexer context-free and simplifies testing: every lexer test can verify token emission in isolation without considering grammar rules.

---

## 6. Open Questions Resolved

From HLD §Open Questions item 1:

> **`lexer` LLD** — Exact placement of `_KEYWORDS` dict (module-level vs class constant) and whether `_scan_ident` is refactored into a helper that handles both keyword lookup and the look-ahead guard for `e`/`E` in numeric scanning.

**Decisions:**

| Question | Decision | Rationale |
|----------|----------|-----------|
| `_KEYWORDS` placement | Module-level | Consistent with `_SINGLE_CHAR`; no `self.` prefix needed; one-line extensibility |
| Merge `_scan_ident` and `e`/`E` rollback guard | No merge | The rollback guard is local to `_scan_number`; merging would couple two unrelated concerns and obscure both |
| Keyword match strategy | Exact string equality via `dict.get` | Identifiers are already fully scanned before lookup; prefix matching would require a separate FSM |

---

## 7. Test Strategy

Tests live in `tests/test_lexer.py`. A `# v0.4.0 — user-defined functions` block is appended; no new file is created (per research #159 decision).

### 7.1 New test cases for v0.4.0

| Test name | Assertion |
|-----------|-----------|
| `test_def_keyword_token` | `Lexer("def").next_token() == Token(TokenType.DEF, "def")` |
| `test_def_in_statement_sequence` | `tokenize("def f ( x ) = x")` produces `[DEF, IDENT("f"), LPAREN, IDENT("x"), RPAREN, EQUALS, IDENT("x"), EOF]` |
| `test_define_still_ident` | `Lexer("define").next_token() == Token(TokenType.IDENT, "define")` |
| `test_default_still_ident` | `Lexer("default").next_token() == Token(TokenType.IDENT, "default")` |
| `test_def_prefix_in_longer_ident` | `Lexer("defun").next_token() == Token(TokenType.IDENT, "defun")` |

### 7.2 Regression coverage

All existing tests in `test_lexer.py` must continue to pass unchanged. Key regression points:

- `test_ident_token` parametrised over `sqrt`, `pi`, `e`, `atan2`, `_var`, `x1` — none of these are in `_KEYWORDS`; all must remain `IDENT`.
- `test_bare_e_after_number` and `test_2e_plus_produces_rollback` — the `e` rollback logic in `_scan_number` is untouched.
- All single-character operator tests — `_SINGLE_CHAR` is untouched.

### 7.3 Test implementation notes

- Use the existing `tokenize()` helper (defined at the top of `test_lexer.py`) for multi-token assertions.
- New tests use the same parametrised or individual-function pattern as the surrounding tests; individual functions are preferred for the keyword-disambiguation cases since the intent is clearer than parametrising over `("define", IDENT), ("default", IDENT), ...`.

---

## 8. Implementation Checklist

1. Add `DEF = auto()` to `TokenType` after `EQUALS`.
2. Add `_KEYWORDS: dict[str, TokenType] = {"def": TokenType.DEF}` at module level, after `_SINGLE_CHAR`.
3. Replace the `return` line in `_scan_ident` with the keyword-lookup idiom shown in §3.2.
4. No other changes to `lexer.py`.
5. Add the `# v0.4.0 — user-defined functions` test block to `tests/test_lexer.py` with the five test cases in §7.1.

Total diff: ~6 lines changed in `lexer.py`, ~20 lines added in `test_lexer.py`.
