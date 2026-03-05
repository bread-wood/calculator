# Research: Lexer Strategy for `def` Keyword — Reserved Token vs Contextual IDENT

**Issue:** #153
**Date:** 2026-03-05
**Milestone:** v0.4.0

---

## Summary

**Recommendation: Add `DEF` as a reserved `TokenType` variant.** The lexer should emit `DEF` whenever it scans the string `def` as an identifier. This is the cleaner design, has negligible regression risk, and positions the lexer correctly for future keywords.

---

## Question 1 — Is `def` currently a valid variable name in v0.3.x?

**Finding: Yes — but no existing code or test uses it.**

The v0.3.x lexer (`src/calc/lexer.py:_scan_ident`) produces `IDENT` for any alphabetic sequence. There is no keyword table. `def` therefore tokenises as `IDENT("def")`, and the parser's `_parse_statement` (parser.py:57–67) permits any `IDENT` followed by `EQUALS` as an assignment target, so `def = 5` would parse and evaluate as a variable assignment today.

A full audit of `tests/test_lexer.py`, `tests/test_parser.py`, `tests/test_evaluator.py`, and `tests/test_cli.py` found **zero tests** that use `def` as a variable name or rely on it producing `IDENT`. The named identifiers in the test suite are: `x`, `y`, `z`, `a`, `b`, `sqrt`, `pi`, `e`, `atan2`, `_var`, `x1`.

**Regression concern: Low.** Reserving `def` silently breaks programs that assign to a variable named `def`. No such program exists in the test suite, and `def` is not listed as a named constant or built-in function anywhere in the codebase. Existing v0.3.x success criteria (all present in the test suite) are unaffected.

---

## Question 2 — Reserved keyword token or contextual IDENT?

### Option A — Reserved keyword: add `DEF` to `TokenType`

`_scan_ident` checks the scanned text against a keyword table and emits `DEF` instead of `IDENT` when the text is exactly `"def"`. The parser dispatches on `current.type == TokenType.DEF` to enter `_parse_funcdef`.

**Pros:**
- Parser logic is explicit and type-safe; no string comparisons anywhere in the parser.
- `def` cannot accidentally be interpreted as a `Name` node or assignment target; the grammar is enforced at the token level.
- Extending to future keywords (e.g. `let`, `import`, `return`) requires only a one-line addition to the keyword table — no parser changes.
- Consistent with standard language-implementation practice.

**Cons:**
- Breaking change: `def = 5` ceases to be valid. (See Question 1 — zero practical impact.)

### Option B — Contextual keyword: keep `def` as `IDENT`

The parser checks `current.type == IDENT and current.value == "def"` to recognise a definition statement.

**Pros:**
- No lexer change; backwards-compatible with the theoretical `def = 5` assignment.

**Cons:**
- String comparisons must be added wherever the parser handles `IDENT` tokens. At minimum `_parse_statement` and `_parse_primary` need guards to prevent `def` being parsed as a `Name` node.
- The grammar intent is implicit. Readers of the parser must understand that a particular `IDENT` value has special meaning.
- Each future keyword requires revisiting every parser method that touches `IDENT`, rather than a single dispatch on token type.

**Verdict: Option A is preferred.** The backwards-compatibility cost is zero in practice, and the implementation and maintenance cost of Option B is ongoing.

---

## Question 3 — Impact on assignment disambiguation

The current `_parse_statement` uses a one-token lookahead (`_peek_next()`) to distinguish assignment from expression:

```python
if self._current.type == TokenType.IDENT and self._peek_next().type == TokenType.EQUALS:
    # assignment
```

**With `DEF` as a reserved token (Option A):**

The parser sees `DEF` as the first token and can dispatch immediately, without inspecting the lookahead at all:

```python
if self._current.type == TokenType.DEF:
    return self._parse_funcdef()
if self._current.type == TokenType.IDENT and self._peek_next().type == TokenType.EQUALS:
    return self._parse_assignment()
return self._parse_expr()
```

No increase in lookahead depth. The existing `_peek_next()` mechanism is sufficient.

**With contextual keyword (Option B):**

The parser would need to check `current.value == "def"` AND inspect `_peek_next()` to decide between `def f(x) = ...` (funcdef) and `def = 5` (assignment):

```python
if self._current.type == TokenType.IDENT and self._current.value == "def":
    if self._peek_next().type == TokenType.IDENT:
        return self._parse_funcdef()
    # fall through — treat as assignment or expression

if self._current.type == TokenType.IDENT and self._peek_next().type == TokenType.EQUALS:
    return self._parse_assignment()
```

Technically still one token of lookahead, but the decision tree is more complex and `def` gets treated as simultaneously a potential keyword and a potential variable name. The grammar specification explicitly writes `def` as a keyword (docs/specs/v0.4.0.md line: `'def' IDENT '(' ...`); the parser should reflect that.

---

## Question 4 — Other future keywords

The v0.4.0 spec (docs/specs/v0.4.0.md, Key Unknowns §1) mentions a future persistent REPL environment. Realistic keyword candidates for subsequent milestones include:

| Keyword   | Likely purpose                              |
|-----------|---------------------------------------------|
| `let`     | Immutable binding (alternative to `=` assignment) |
| `import`  | Loading external definitions in REPL context |
| `return`  | Multi-statement function bodies (post-v0.4.x) |
| `if`/`else` | Conditional expressions (post-v0.4.x)   |

With the reserved-keyword approach, adding any of these requires exactly one line in the keyword table:

```python
_KEYWORDS: dict[str, TokenType] = {
    "def": TokenType.DEF,
    # future: "let": TokenType.LET, etc.
}
```

With the contextual approach, each new keyword requires auditing the parser for every code path that checks `current.type == IDENT`.

---

## Recommendation

**Implement `DEF` as a reserved `TokenType` variant.**

### Lexer change (src/calc/lexer.py)

1. Add `DEF = auto()` to `TokenType`.
2. Add a module-level keyword table:
   ```python
   _KEYWORDS: dict[str, TokenType] = {
       "def": TokenType.DEF,
   }
   ```
3. In `_scan_ident`, look up the scanned text before returning:
   ```python
   def _scan_ident(self) -> Token:
       start = self._cursor
       while self._peek().isalnum() or self._peek() == "_":
           self._advance()
       text = self._input[start:self._cursor]
       tt = _KEYWORDS.get(text, TokenType.IDENT)
       return Token(tt, text)
   ```

No other lexer changes are required.

### Parser change

`_parse_statement` gains one additional leading check:

```python
if self._current.type == TokenType.DEF:
    return self._parse_funcdef()
```

The existing `IDENT + EQUALS` assignment path and `_parse_expr` fallthrough are unchanged.

### Test impact

- No existing test uses `def` as a variable or asserts that `def` produces `IDENT`.
- New lexer tests should assert `Lexer("def").next_token() == Token(TokenType.DEF, "def")`.
- `def` appearing as part of a longer identifier (e.g. `default`, `define`) must still produce `IDENT` — the keyword match is exact, so this is automatically correct.

---

## Follow-up issues

None required from this research. The lexer and parser changes described above are self-contained and can be implemented directly in the v0.4.0 implementation issue.
