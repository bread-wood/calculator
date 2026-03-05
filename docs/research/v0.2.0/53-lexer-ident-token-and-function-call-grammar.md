# Research: Lexer IDENT Token and Function-Call Grammar Extension

**Issue:** #53
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## Summary

This document analyses the minimal changes required to `lexer.py` and `parser.py` to support identifier tokens (for constants such as `pi` and function calls such as `sqrt(9)`), and identifies which existing tests are affected.

---

## 1. Lexer Changes

### 1.1 New `TokenType.IDENT`

Add a single member to `TokenType`:

```python
IDENT = auto()
```

### 1.2 New scan path in `next_token`

In `Lexer.next_token`, insert a branch before the fall-through `UNKNOWN` return:

```python
if ch.isalpha() or ch == "_":
    return self._scan_ident()
```

### 1.3 `_scan_ident` helper

```python
def _scan_ident(self) -> Token:
    start = self._cursor
    while self._peek().isalnum() or self._peek() == "_":
        self._advance()
    return Token(TokenType.IDENT, self._input[start:self._cursor])
```

### 1.4 Exponent-notation ambiguity (`1e10`)

`_scan_number` already consumes the `e`/`E` character **inside** its own loop (lines 81–86) before `next_token` can ever dispatch on it. Therefore an exponent suffix is never presented to the identifier branch: **no ambiguity exists and no special guarding is needed.**

The only scenario to verify is a bare `e` or `E` not preceded by digits, e.g. `e + 1`. In that case `next_token` is called when `_cursor` points at `e`, which is not a digit or `.`, so `_scan_number` is never entered; the identifier branch fires correctly and produces `Token(IDENT, "e")`. This is the desired behaviour (such a token would be rejected by the parser unless `e` is registered as a known name).

### 1.5 Impact on `UNKNOWN`

Only characters that are **not** `isalpha()` and **not** `_` reach the `UNKNOWN` return. The existing `test_unknown_character` test uses `@` and `$` — neither is alphabetic, so **both tests remain green without modification**.

No previously-`UNKNOWN` character that should stay `UNKNOWN` is reclassified.

---

## 2. Parser Changes

### 2.1 New AST nodes

Add two dataclasses alongside `Number`, `BinaryOp`, `UnaryOp`:

```python
@dataclass
class Name:
    name: str          # bare constant reference: pi, e, …

@dataclass
class Call:
    func: str          # function name: sqrt, abs, …
    args: list[ASTNode]
```

Update the `ASTNode` type alias:

```python
ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

### 2.2 Extension of `_parse_primary`

The existing `_parse_primary` already handles `NUMBER` and `LPAREN`; adding `IDENT` handling requires **only a new branch at the end of that method**, before the final `raise UnexpectedToken()`:

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

No other production rule (`_parse_expr`, `_parse_term`, `_parse_factor`, `_parse_unary`) needs modification. The unary/factor chain reaches `_parse_primary` unchanged.

### 2.3 `_parse_arglist` local helper

A private method added to `Parser`:

```python
def _parse_arglist(self) -> list[ASTNode]:
    args: list[ASTNode] = []
    if self._current.type == TokenType.RPAREN:
        return args          # zero-argument call: f()
    args.append(self._parse_expr())
    while self._current.type == TokenType.COMMA:
        self._advance()
        args.append(self._parse_expr())
    return args
```

This requires adding `TokenType.COMMA` to the lexer (single-char token `,`) if multi-argument functions are in scope for v0.2.0. For the immediate goal of `sqrt(9)` (single argument), COMMA can be deferred and the helper simplified to:

```python
def _parse_arglist(self) -> list[ASTNode]:
    if self._current.type == TokenType.RPAREN:
        return []
    return [self._parse_expr()]
```

`_parse_expr`, `_parse_term`, and `_parse_unary` are **not touched**.

---

## 3. Evaluator Changes (out of scope for this issue, noted for completeness)

`evaluator.py` will need a lookup table for constants (`{"pi": math.pi, "e": math.e}`) and functions (`{"sqrt": math.sqrt, "abs": abs}`), and `isinstance` branches for `Name` and `Call`. This is separate from the lexer/parser work.

A new `UnknownName` / `UnknownFunction` error class in `errors.py` will be required.

---

## 4. Existing Tests Affected

| File | Test | Status after change |
|---|---|---|
| `tests/test_lexer.py` | `test_unknown_character` (uses `@`) | **Unaffected** — `@` is not alphabetic |
| `tests/test_lexer.py` | `test_unknown_then_eof` (uses `$`) | **Unaffected** — `$` is not alphabetic |
| `tests/test_lexer.py` | All other tests | **Unaffected** |
| `tests/test_parser.py` | All tests | **Unaffected** — no IDENT input used |
| `tests/test_evaluator.py` | All tests | **Unaffected** |

No existing test needs to be updated. All green tests remain green.

New tests that will need to be written (in implementation issues):
- Lexer: `IDENT` tokens for single word, multi-char, underscore, digit-suffix identifiers.
- Lexer: exponent notation (`1e10`, `2.5E-3`) still produces a single `NUMBER` token.
- Parser: `Name` node for bare identifier; `Call` node for `name(expr)`.
- Evaluator: `pi`, `e`, `sqrt(9)`, zero-arg and unknown-name error cases.

---

## 5. Answers to Research Questions

**Q1: Does the recursive-descent structure accommodate both cases without restructuring other production rules?**
Yes. Both the bare-name and function-call cases are fully handled by a new branch inside `_parse_primary`. No other rule changes.

**Q2: Can arglist parsing be added as a local helper without touching `_parse_expr`, `_parse_term`, or `_parse_unary`?**
Yes. `_parse_arglist` calls `_parse_expr` (which already exists) for each argument. The helper is self-contained in `Parser` and does not change any existing method signatures.

**Q3: Does scanning identifiers risk ambiguity with exponent notation?**
No. `_scan_number` consumes `e`/`E` (and any following sign and digits) as part of the number token before control returns to `next_token`. The identifier branch is only reached when `next_token` begins dispatch on a fresh character.

**Q4: Does adding IDENT require changes to UNKNOWN handling or break existing tests?**
No. Only alphabetic characters and `_` are redirected from `UNKNOWN` to `IDENT`. Every character currently producing `UNKNOWN` that is tested (`@`, `$`) is non-alphabetic and continues to produce `UNKNOWN`.

---

## 6. Minimal Diff Summary

**`lexer.py`** — 2 additions:
1. `IDENT = auto()` in `TokenType`.
2. `_scan_ident` method + dispatch branch in `next_token` (≈8 lines).

**`parser.py`** — 3 additions:
1. `Name` and `Call` dataclasses + updated `ASTNode` alias (≈8 lines).
2. IDENT branch in `_parse_primary` (≈7 lines).
3. `_parse_arglist` helper method (≈6 lines).

Total: **≈29 new lines**, zero deletions, zero modifications to existing logic.
