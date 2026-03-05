# Research: `_scan_number` Consumes e/E Unconditionally — Malformed Token on Input Like `2e`

**Issue:** #66
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## 1. Bug Confirmation

`_scan_number` (lexer.py:81–86) advances past `e`/`E` regardless of whether any digits follow:

```python
if self._peek() in ("e", "E"):
    self._advance()          # e/E consumed unconditionally
    if self._peek() in ("+", "-"):
        self._advance()
    while self._peek().isdigit():
        self._advance()
```

Input `2e` produces `Token(NUMBER, "2e")`. In `_parse_primary` (parser.py:87), `float("2e")` raises a bare `ValueError` — not a `CalcError` subclass — which propagates uncaught out of `main()` instead of printing `error: unexpected token` and exiting 1. Verified empirically:

```
ValueError: could not convert string to float: '2e'
```

---

## 2. Fix Options

### Option A — Look-ahead guard in `_scan_number` (preferred)

Before consuming `e`/`E`, check that at least one digit follows (after an optional `+`/`-`). If no digit follows, leave `e`/`E` unconsumed so `next_token` dispatches it as `IDENT("e")`.

```python
if self._peek() in ("e", "E"):
    saved = self._cursor
    self._advance()                    # tentatively consume e/E
    if self._peek() in ("+", "-"):
        self._advance()
    if self._peek().isdigit():
        while self._peek().isdigit():
            self._advance()
    else:
        self._cursor = saved           # rollback — leave e/E for IDENT branch
```

Result for `2e`: lexer produces `Token(NUMBER, "2")` then (via `next_token`) `Token(IDENT, "e")`. The parser sees two consecutive primaries and raises `UnexpectedToken` → `error: unexpected token`. ✓

### Option B — Parser-side `try/except ValueError`

Wrap `float(token.value)` in `_parse_primary`:

```python
try:
    value = float(self._advance().value)
except ValueError:
    raise UnexpectedToken()
```

Result for `2e`: the malformed `NUMBER("2e")` token is consumed and `UnexpectedToken` is raised → `error: unexpected token`. ✓

---

## 3. Comparison

| Criterion | Option A (look-ahead guard) | Option B (parser catch) |
|---|---|---|
| Root cause fixed | Yes — lexer never emits malformed NUMBER | No — lexer still emits `NUMBER("2e")` |
| Token stream for `2e` | `NUMBER("2")`, `IDENT("e")` | `NUMBER("2e")` (consumed, error raised) |
| Lines changed | ~6 lines in `_scan_number` | ~3 lines in `_parse_primary` |
| v0.2.0 alignment | Correct: `e` surfaces as IDENT for evaluator lookup | Incorrect: `e` never surfaces as IDENT |
| Valid sci-notation affected | No (see §4) | No |

**Recommendation: Option A.** v0.2.0 introduces `e` as a named constant. Option B discards the `e` inside a bad token and never gives the parser a chance to treat it as an identifier. Option A fixes the lexer contract (NUMBER tokens must be parseable by `float()`) and correctly surfaces `e` for future IDENT dispatch.

---

## 4. Impact on Valid Scientific Notation

The look-ahead guard only rolls back when no digit follows `e/E` (after optional sign). For all valid exponent forms the guard condition is satisfied immediately:

| Input | After `e/E` tentative advance | Digit present? | Behaviour |
|---|---|---|---|
| `1e10` | peek = `1` | yes | consumed normally, `NUMBER("1e10")` |
| `1e+10` | peek = `+`, then `1` | yes | consumed normally, `NUMBER("1e+10")` |
| `1e-5` | peek = `-`, then `5` | yes | consumed normally, `NUMBER("1e-5")` |
| `1.5E2` | peek = `2` | yes | consumed normally, `NUMBER("1.5E2")` |
| `2e` | peek = `""` (EOF) | no | rollback, `NUMBER("2")` |
| `2e+` | peek = `+`, then `""` | no | rollback, `NUMBER("2")` |
| `2e*3` | peek = `*` | no | rollback, `NUMBER("2")` |

No valid scientific notation is affected. `float()` succeeds on all valid tokens. `2e+` and `2e*3` are degenerate inputs that were also broken before; Option A makes them produce sensible error messages as well.

---

## 5. Existing Test Coverage

No existing test exercises `2e`-style input.

| File | Relevant test | Status after Option A |
|---|---|---|
| `tests/test_lexer.py` | `test_number_literals` — `42`, `3.14`, `.5`, `3.`, `100` | **Unaffected** — no exponent input |
| `tests/test_lexer.py` | `test_unknown_character` (`@`) | **Unaffected** |
| `tests/test_lexer.py` | `test_unknown_then_eof` (`$`) | **Unaffected** |
| `tests/test_parser.py` | `test_parse_errors` — `"2 +"`, `"2 3"`, etc. | **Unaffected** |
| `tests/test_parser.py` | All passing tests | **Unaffected** |

No existing test needs to be updated. The fix is purely additive (new guard path in `_scan_number`).

New tests to add in the implementation issue:

- Lexer: `2e` tokenizes as `[NUMBER("2"), IDENT("e"), EOF]`
- Lexer: `2e+` tokenizes as `[NUMBER("2"), IDENT("e"), PLUS("+"), EOF]`
- Lexer: `1e10` still tokenizes as `[NUMBER("1e10"), EOF]` (regression guard)
- Parser/CLI: `2e` produces `error: unexpected token`, exit 1 (not `ValueError`)

---

## 6. Scope for v0.2.0

**This fix is required for v0.2.0 acceptance**, not deferrable.

Without it, a user who types `2e` (intending `2 * e`) will receive an unhandled Python `ValueError` rather than the documented `error: unexpected token` message. Since v0.2.0 introduces `e` as a named constant, this mis-typed expression becomes a realistic and foreseeable input. The v0.2.0 acceptance criteria require all invalid expressions to produce a `CalcError`-derived message; a bare `ValueError` crash fails that requirement.

The fix is small and self-contained (≈6 lines in `_scan_number`), carries no risk to valid scientific notation, and aligns with the lexer contract established by the rest of the codebase.

---

## 7. Summary

`_scan_number` must be given a look-ahead guard that rolls back the `e`/`E` advance when no digit (after optional sign) follows. This makes the lexer emit a well-formed `NUMBER` token and leaves `e`/`E` in the stream for IDENT dispatch, so `2e` results in `error: unexpected token` instead of an uncaught `ValueError`. The change has zero impact on valid scientific notation and zero impact on existing passing tests. It is in scope for v0.2.0.
