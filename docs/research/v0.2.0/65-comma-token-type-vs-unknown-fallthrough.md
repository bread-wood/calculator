# Research: COMMA token type vs UNKNOWN fallthrough for arglist parsing

**Issue:** #65
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## Summary

**Recommendation: Option A — add `COMMA` to `TokenType` and `_SINGLE_CHAR`.**

The comma separator for multi-argument function calls (e.g. `pow(2, 10)`, `atan2(1, 1)`)
should be a first-class `TokenType.COMMA` entry, not matched via `UNKNOWN` value inspection.
No existing test requires modification.

---

## 1. Codebase Baseline

The v0.1.x `lexer.py` has:

```python
class TokenType(Enum):
    NUMBER = auto()
    PLUS   = auto()
    MINUS  = auto()
    STAR   = auto()
    SLASH  = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF    = auto()
    UNKNOWN = auto()

_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
}
```

`next_token()` dispatches on `_SINGLE_CHAR`, then on digit/`.` for numbers, then falls
through to `Token(TokenType.UNKNOWN, ch)` for everything else. A bare `,` therefore
currently produces `Token(UNKNOWN, ",")`.

Research #53 already anticipates the need:

> "This requires adding `TokenType.COMMA` to the lexer (single-char token `,`) if
> multi-argument functions are in scope for v0.2.0."

---

## 2. Option Analysis

### Option A — First-class `COMMA` token

**Lexer changes:**

```python
# TokenType
COMMA = auto()

# _SINGLE_CHAR
",": TokenType.COMMA,
```

**Parser `_parse_arglist` check:**

```python
while self._current.type == TokenType.COMMA:
    self._advance()
    args.append(self._parse_expr())
```

### Option B — `UNKNOWN` + value check

No lexer change. Parser check:

```python
while (self._current.type == TokenType.UNKNOWN
       and self._current.value == ","):
    self._advance()
    args.append(self._parse_expr())
```

---

## 3. Answers to Research Questions

### Q1: Does `_parse_arglist` need COMMA as a first-class `TokenType`, or is `UNKNOWN+value` sufficient?

Technically either works for the narrow case of `pow(2, 10)`. However, Option A is
strongly preferred for the following reasons:

1. **Consistency with the existing design.** Every syntactically meaningful single-character
   token in the language (`+`, `-`, `*`, `/`, `(`, `)`) already has its own `TokenType`
   entry and appears in `_SINGLE_CHAR`. The comma plays an equivalent role in arglist
   syntax. Treating it differently violates the established pattern without benefit.

2. **Clarity of intent.** A type-only check (`self._current.type == TokenType.COMMA`) is
   self-documenting. The dual-field check in Option B (`type == UNKNOWN and value == ","`)
   leaks knowledge of the lexer's fallthrough mechanism into the parser, coupling the two
   modules in an undocumented way.

3. **Token streams are more useful.** Any future tooling (formatters, syntax highlighters,
   serializers) that iterates tokens will correctly identify commas without needing to
   special-case the `UNKNOWN` fallthrough.

4. **Error messages.** When a comma appears in an illegal position, an error system that
   inspects `TokenType` can produce a targeted message ("unexpected comma") rather than a
   generic "unexpected character".

### Q2: Does Option B risk treating an intended-unknown character (e.g. `$`) as a comma separator?

No. The dual-field guard (`value == ","`) is logically sufficient: `$` has `value == "$"`,
not `","`, so it cannot be mistaken for a comma separator. However, Option B's weakness
is **conceptual contamination**, not a concrete collision bug: the parser grows a hidden
dependency on the incidental value strings produced by the lexer's fallthrough path.
If the lexer is later refactored (e.g. to intern values or use a separate `raw` field),
Option B silently breaks.

### Q3: If `COMMA` is added to `TokenType`, does any existing test need updating?

**No existing test requires modification.**

The two tests that exercise `UNKNOWN` are:

| Test | Input | Outcome after adding `COMMA` |
|------|-------|------------------------------|
| `test_unknown_character` | `@` | Still `UNKNOWN` — `@` is not in `_SINGLE_CHAR` |
| `test_unknown_then_eof` | `$` | Still `UNKNOWN` — `$` is not in `_SINGLE_CHAR` |

Neither test uses `,` as input. No parametrised `test_single_char_operators` case covers
`,` either. Adding `COMMA` only reclassifies `,` from `UNKNOWN` to `COMMA`; all other
characters are unaffected.

New tests that implementation issues should add:

- Lexer: `Token(TokenType.COMMA, ",")` for input `","`.
- Lexer: multi-token sequence `"2,3"` → `NUMBER COMMA NUMBER EOF`.
- Parser: `pow(2, 10)` and `atan2(1, 1)` produce `Call` nodes with two-element `args`
  lists.
- Parser: `f(,)` and `f(1,)` raise `UnexpectedToken`.

### Q4: Is there a precedent for "operator-like" characters that are NOT in `_SINGLE_CHAR`?

Yes — the comma itself is the only such precedent in the current lexer. All other
syntactically meaningful single characters (`+`, `-`, `*`, `/`, `(`, `)`) are in
`_SINGLE_CHAR`. The comma's absence is an omission that predates multi-argument function
support, not a deliberate architectural choice. Option A corrects the omission; Option B
papers over it.

---

## 4. Recommended Implementation

**`lexer.py` — 2-line change:**

```python
# 1. TokenType — add after RPAREN:
COMMA = auto()

# 2. _SINGLE_CHAR — add entry:
",": TokenType.COMMA,
```

**`parser.py` — `_parse_arglist` (from research #53, amended):**

```python
def _parse_arglist(self) -> list[ASTNode]:
    args: list[ASTNode] = []
    if self._current.type == TokenType.RPAREN:
        return args
    args.append(self._parse_expr())
    while self._current.type == TokenType.COMMA:
        self._advance()
        args.append(self._parse_expr())
    return args
```

Total change: 2 new lines in `lexer.py`, zero modifications to existing logic,
zero existing tests broken.

---

## 5. Verdict

| Criterion | Option A (COMMA TokenType) | Option B (UNKNOWN + value) |
|-----------|---------------------------|---------------------------|
| Consistent with lexer design | Yes | No |
| Parser-lexer coupling | Minimal (type only) | Hidden (value string) |
| Risk of misclassifying other chars | None | None |
| Existing tests affected | None | None |
| Future refactoring safety | Safe | Fragile |

**Option A is the correct choice.** Add `COMMA = auto()` to `TokenType` and
`",": TokenType.COMMA` to `_SINGLE_CHAR`. The `_parse_arglist` helper then uses a
clean type-only check. No existing test requires modification.
