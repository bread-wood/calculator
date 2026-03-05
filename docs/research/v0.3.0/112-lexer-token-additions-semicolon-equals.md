# Research: Lexer Token Additions — SEMICOLON and EQUALS

**Issue:** #112
**Date:** 2026-03-05
**Milestone:** v0.3.0

---

## Summary

Both `;` (SEMICOLON) and `=` (EQUALS) are safe to add as single-character entries in `_SINGLE_CHAR` in `src/calc/lexer.py`. No existing tests assert `UNKNOWN` for either character. No `==` token is planned or implemented. The exponent rollback path is unaffected. No code depends on specific `TokenType` integer values.

---

## Question 1 — Conflict with existing tests

**Finding: No conflicts. No tests need updating.**

A full audit of `tests/test_lexer.py` and `tests/test_parser.py` found:

- No test passes `;` or `=` as input.
- No test asserts that either character produces `UNKNOWN`.
- The only `UNKNOWN` assertions use `@` (line 99–102) and `$` (line 106–108) as example unknown characters. These are unaffected by the new tokens.
- The parser error tests (`test_parse_errors`, `test_parse_errors_v0_2_0`, `test_trailing_comma_is_error`) use expressions like `"2 +"`, `"(2 + 3"`, `"2 3"`, `"2 + )"`, `"(2 + 3 4"`, `"sqrt("`, `"sqrt(9"`, `"sqrt(9 4"`, and `"f(1,)"`. None contain `;` or `=`.

**Conclusion:** Adding SEMICOLON and EQUALS will not break any existing test.

---

## Question 2 — `=` vs `==` (equality operator)

**Finding: No `==` token is planned; single-char `=` is correct.**

The codebase has no equality operator. A review of:

- `src/calc/lexer.py` — `TokenType` has no `EQEQ` or `EQUAL` member.
- `src/calc/parser.py` — no equality comparison rules.
- `docs/` — no design document or spec mentioning `==` or equality for any milestone, including v0.3.0.

The v0.3.0 grammar uses `=` as an assignment separator (e.g., `let x = expr`), not as an equality test. There is no planned `==` operator requiring lookahead. Single-character tokenisation is correct and sufficient.

**Conclusion:** Implement `=` as a plain single-char token `EQUALS`. No lookahead required now or for any currently planned milestone.

---

## Question 3 — Exponent rollback interaction with EQUALS

**Finding: The rollback path is unaffected by adding EQUALS.**

The exponent rollback in `_scan_number` (lines 61–68 of `lexer.py`) works as follows:

1. If the current character is `e` or `E`, save `self._cursor` as `saved`.
2. Tentatively advance past `e/E`.
3. Optionally advance past `+` or `-`.
4. If the next character is **a digit**, consume the full exponent — valid scientific notation.
5. Otherwise, **roll back** `self._cursor = saved` — the `e/E` is left unconsumed.

After rollback, `_scan_number` returns the number without the exponent. The lexer's main `next_token()` loop then reads the `e/E` character next; since it satisfies `ch.isalpha()`, it enters `_scan_ident` and produces an `IDENT` token.

For the input `1e=2`:

| Step | Cursor | Action | Token |
|------|--------|--------|-------|
| 1 | 0 | `_scan_number` consumes `1` | — |
| 2 | 1 | sees `e`, saves cursor=1, advances to 2 | — |
| 3 | 2 | next char is `=` — not `+`, `-`, or digit | — |
| 4 | 1 | rollback: cursor reset to 1 | `NUMBER("1")` returned |
| 5 | 1 | `next_token`: `e` → `_scan_ident` | `IDENT("e")` |
| 6 | 2 | `next_token`: `=` → `_SINGLE_CHAR` lookup | `EQUALS("=")` |
| 7 | 3 | `next_token`: `2` → `_scan_number` | `NUMBER("2")` |

The rollback logic does **not** inspect `=` at all during the decision — it only checks `self._peek().isdigit()`. Adding `=` to `_SINGLE_CHAR` has zero effect on the rollback branch. The sequence for `1e=2` would be `[NUMBER("1"), IDENT("e"), EQUALS("="), NUMBER("2")]`, which is correct and consistent with existing rollback behaviour demonstrated by `test_2e_plus_produces_rollback` and `test_2e_star_produces_rollback`.

**Conclusion:** Safe. No interaction between EQUALS and the exponent rollback.

---

## Question 4 — TokenType enum ordering

**Finding: No code depends on specific integer values of `TokenType` members.**

`TokenType` uses `auto()` (lines 7–17 of `lexer.py`), which assigns sequential integers starting from 1. A full search across:

- `src/calc/lexer.py` — tokens compared by identity (`t.type == TokenType.X`), never by integer value.
- `src/calc/parser.py` — same pattern; no numeric comparisons or ordinal arithmetic.
- `tests/test_lexer.py`, `tests/test_parser.py`, `tests/test_errors.py`, `tests/test_evaluator.py`, `tests/test_cli.py` — all comparisons use `TokenType.X` named members.

No serialisation, protocol encoding, or lookup-by-integer is present in the codebase.

**Conclusion:** Appending `SEMICOLON` and `EQUALS` anywhere in the `TokenType` enum (including at the end) is safe. Ordinal values are irrelevant.

---

## Recommendation

Add the following two entries to `_SINGLE_CHAR` in `src/calc/lexer.py`:

```python
";": TokenType.SEMICOLON,
"=": TokenType.EQUALS,
```

And add the corresponding members to `TokenType`:

```python
SEMICOLON = auto()
EQUALS = auto()
```

No test changes are required. No lookahead logic is needed. The change is a straightforward two-line addition to `_SINGLE_CHAR` plus two lines to `TokenType`.

---

## Follow-up issues

None. All four questions are fully resolved with safe outcomes.
