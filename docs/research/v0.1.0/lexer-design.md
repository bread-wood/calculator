# Lexer Design Research — v0.1.0

**Issue:** #6
**Date:** 2026-03-04
**Status:** Complete

---

## Question

How should the lexer be structured to correctly tokenize all valid input, produce actionable error tokens for unknown characters, and remain extensible to identifiers (function names, variables) in future versions?

---

## Recommendation

**Iterator/scanner abstraction with character-by-character dispatch, emitting UNKNOWN tokens for unrecognised characters.**

A `Scanner` struct wrapping a string cursor with `peek()` and `advance()` methods gives a clean, independently testable boundary. Dispatch uses a `switch`/`if` on the current character — no regex, no external dependencies.

---

## Token Set (v0.1.0)

| Token type | Lexeme | Notes |
|------------|--------|-------|
| `NUMBER`   | `3`, `3.14`, `.5`, `3.` | See number parsing section |
| `PLUS`     | `+` | |
| `MINUS`    | `-` | Lexer emits; parser disambiguates unary vs binary |
| `STAR`     | `*` | |
| `SLASH`    | `/` | |
| `LPAREN`   | `(` | |
| `RPAREN`   | `)` | |
| `EOF`      | — | End of input |
| `UNKNOWN`  | any unrecognised character | Carries the offending character |

---

## Options Evaluated

### 1. Character-by-character with switch/if (recommended)

The lexer holds a string and an integer cursor position. `peek()` returns the character at the cursor without advancing; `advance()` returns it and increments the cursor.

```
nextToken():
  skip whitespace
  switch peek():
    '+' → advance, return PLUS
    '-' → advance, return MINUS
    '*' → advance, return STAR
    '/' → advance, return SLASH
    '(' → advance, return LPAREN
    ')' → advance, return RPAREN
    '0'–'9', '.' → scanNumber()
    '\0'/end → return EOF
    default → advance, return UNKNOWN(char)
```

**Pros:**
- Zero dependencies; pure stdlib.
- Each token type is a distinct, named branch — easy to read and debug.
- Adding new single-character tokens (e.g. `=`, `,`) = one new `case`.
- Adding identifier tokens = one new branch for `[a-zA-Z_]` that calls `scanIdent()`.
- Independently unit-testable: instantiate a Scanner with a string, call `nextToken()` in a loop.

**Cons:**
- Slightly more code than regex for number literals, but number parsing is simple enough (see below) that this is not a practical disadvantage.

**Extension cost:** Minimal. Each new token type requires one new branch. `scanIdent()` is a `while isAlphaNum` loop, identical in structure to `scanNumber()`.

---

### 2. Regex-based

Use a regular expression to match the longest token at the current cursor position.

**Pros:**
- Number literal pattern can be expressed concisely.
- Less code for the number branch.

**Cons:**
- Standard libraries differ in regex API across languages; may complicate portability.
- Regex errors surface at runtime, not compile time.
- Harder to unit-test individual token branches in isolation.
- No meaningful advantage over character-by-character for a token set this small.

**Verdict:** Not recommended. Added complexity with no benefit at this scale.

---

### 3. Iterator/scanner abstraction only (as a refinement of option 1)

This is the chosen approach — option 1 *with* an explicit `Scanner` type. The scanner is the only object that owns the input string and cursor. `nextToken()` is a method on the scanner.

Separating the scanner from the parser means:
- Lexer unit tests need no parser.
- Parser unit tests can use a fake/stub token stream.
- Future refactors (e.g. tracking line/column for error messages) are confined to the scanner.

---

## Number Parsing

### Integers

Consume digits while `isDigit(peek())`.

### Floats

Consume digits, then optionally consume a `.` followed by more digits.

**Edge cases — decision:**

| Input | Behaviour | Rationale |
|-------|-----------|-----------|
| `3.14` | Valid float `3.14` | Standard |
| `3.` | Valid float `3.0` | Trailing dot accepted; parser sees a complete number |
| `.5` | Valid float `0.5` | Leading dot accepted; common in calculator input |
| `..` | First `.` begins a number scan; no digit follows → emit `NUMBER(".")` then `UNKNOWN('.')` | Degenerate input; parser will reject the malformed number |

Accepting `3.` and `.5` is consistent with how most calculators and many languages (Python, C) treat these forms. Rejecting them would silently break expressions like `1./2` that users might type.

**Algorithm:**

```
scanNumber():
  start = cursor
  if peek() == '.':
    advance  // leading dot
    consume digits
  else:
    consume digits
    if peek() == '.':
      advance
      consume digits  // may be zero digits (trailing dot)
  return NUMBER(input[start..cursor])
```

### Unary minus

The lexer always emits `MINUS`. The parser determines whether it is unary (nothing to the left, or the left is an operator/LPAREN) or binary. This is the standard separation of concerns; the lexer has no context about what preceded the token.

---

## Unknown Token Handling

**Recommendation: emit `UNKNOWN(char)` rather than throwing immediately.**

Rationale:
- The spec error message is `error: unexpected token`. This can be produced equally by either approach.
- Emitting a token allows the parser to accumulate and report the specific offending character.
- It keeps the lexer's contract uniform: callers always get a token stream, never an exception mid-stream. This simplifies unit testing.
- The parser still errors on the first `UNKNOWN` token encountered — behaviour is identical from the user's perspective.

Implementation: advance past the character, return `Token{type: UNKNOWN, value: char}`. The parser, upon seeing `UNKNOWN`, halts and returns `error: unexpected token`.

---

## Whitespace

Skip silently. In `nextToken()`, before dispatch, advance past any run of space, tab, or other whitespace characters. No newline handling is needed (single-line expression input).

---

## Extensibility to Identifiers

Adding identifiers (for `sin`, `sqrt`, variable names) requires:

1. Add `IDENT` to the token type enum.
2. In `nextToken()`, add a branch for `[a-zA-Z_]` that calls `scanIdent()`:
   ```
   scanIdent():
     consume while isAlphaNum or '_'
     return IDENT(lexeme)
   ```
3. No other lexer code changes.

The `UNKNOWN` branch continues to handle anything not covered by the above — no change needed there either.

---

## Final Structure

```
Scanner:
  input: string
  cursor: int

  peek() → char
  advance() → char
  nextToken() → Token

Token:
  type: TokenType
  value: string  // the raw lexeme

TokenType:
  NUMBER | PLUS | MINUS | STAR | SLASH | LPAREN | RPAREN | EOF | UNKNOWN
```

The lexer exposes a single public method: `nextToken()`. The parser calls it on demand (lazy/pull model), which means no intermediate token slice needs to be allocated before parsing begins.

---

## Acceptance Criteria Review

| Criterion | Met? | Notes |
|-----------|------|-------|
| All spec token types correctly identified | Yes | NUMBER, PLUS, MINUS, STAR, SLASH, LPAREN, RPAREN, EOF |
| Number literals (int and float) parsed accurately | Yes | Handles `3`, `3.14`, `.5`, `3.` |
| Unknown characters produce the specified error | Yes | UNKNOWN token → parser emits `error: unexpected token` |
| Lexer is independently unit-testable | Yes | Scanner struct has no parser dependency |
| Adding identifier tokens requires minimal changes | Yes | One new branch + `scanIdent()` function |
