# Error Taxonomy and Exit-Code Conventions
**Issue:** #4 | **Milestone:** v0.1.0 | **Date:** 2026-03-04

## Recommendation Summary

Use a single `CalcError` enum (or equivalent tagged union / struct) with one variant per
error class. Bubble errors as return values (not exceptions) all the way to `main`, which
owns the single stderr write and the `exit(1)` call. Use a flat exit-code space (0 / 1)
for v0.1.0 but leave room for extension via the error type itself.

---

## 1. Error Origin Map

| Error message | Origin layer | Notes |
|---|---|---|
| `error: expected a single quoted expression` | **main** — arg-count check | Before any parsing |
| `error: empty expression` | **main** — after arg-count check | `argv[1] == ""` |
| `error: unexpected token` | **Lexer** | Unrecognised character; also emitted by parser on excess tokens after full parse |
| `error: unexpected end of expression` | **Parser** | Expected operand/token but hit EOF |
| `error: division by zero` | **Evaluator** | Integer or float divide by zero |
| `error: overflow` | **Evaluator** | Result outside representable range |

The "no arguments" case (`calc` with nothing) prints **usage** (not `error: …`) per the
spec; it is handled in `main` alongside the too-many-arguments case, which does emit
`error: expected a single quoted expression`.

---

## 2. Error Type Representation

**Recommendation: single `CalcError` enum (tagged union / discriminated union)**

```
CalcError variants:
  UnexpectedToken
  UnexpectedEnd
  DivisionByZero
  Overflow
  EmptyExpression
  ExpectedSingleArg
```

Rationale:
- Each variant maps 1-to-1 to a spec message; no string interpolation needed in v0.1.0.
- Extending to source-location info in future versions is additive: give each variant an
  optional `(line, col, offset)` payload without breaking existing match arms.
- A plain string error type (`&str` / `char *` message) would work today but forecloses
  structured handling (e.g., error codes per class, i18n, machine-readable output).
- An exception-based approach (where supported) conflates control flow with error
  semantics and complicates unit-testing individual layers in isolation.

---

## 3. Propagation Mechanism

**Recommendation: return-value propagation (`Result<T, CalcError>` in Rust; explicit
error-return pointer or `Option<Error>` in C)**

- Each layer (lexer, parser, evaluator) returns either a success value or a `CalcError`.
- Errors propagate upward without being written anywhere until `main`.
- No `setjmp`/`longjmp`; no unchecked exceptions.

This is the only mechanism that keeps stderr writing centralized (see §4) and makes each
layer independently unit-testable by inspecting the returned error variant directly.

---

## 4. stderr Writing Ownership

**Recommendation: centralized in `main`**

```
main
 ├─ arg-count / empty-string check  →  CalcError
 ├─ lexer(input)                    →  Result<tokens, CalcError>
 ├─ parser(tokens)                  →  Result<AST, CalcError>
 ├─ evaluator(AST)                  →  Result<f64, CalcError>
 └─ on any Err: fprintf(stderr, "error: %s\n", message(e)); exit(1)
```

Benefits:
- Tests of lexer / parser / evaluator never touch stderr; they just assert on the returned
  error variant.
- The `error: <description>\n` formatting rule is enforced in exactly one place.
- Swapping stderr for a test buffer (dependency injection) requires changing one call site.

The `message(e)` function (or enum `Display` impl) is the canonical source of verbatim
error strings; it must be the only place those strings appear (DRY for test assertions).

---

## 5. Exit-Code Extensibility

The spec mandates exit 0 on success and exit 1 on any error. For v0.1.0 this is
sufficient. Future versions should **not** introduce new exit codes without a spec update,
because shell scripts that test `$?` treat any non-zero value as failure; introducing exit
2 / 3 could break callers silently.

The recommended approach is to keep exit codes at 0 / 1 and encode richer error
classification in the `CalcError` type. If a future spec mandates distinct codes (e.g.,
exit 2 for input errors vs. exit 3 for arithmetic errors), the `main` dispatcher already
has the enum variant to switch on — no layer below `main` needs to change.

---

## 6. Complete Failure-Mode Table

| Invocation | Expected stderr | Exit |
|---|---|---|
| `calc` | `usage: calc '<expression>'` | 1 |
| `calc 1+1 2+2` | `error: expected a single quoted expression` | 1 |
| `calc ''` | `error: empty expression` | 1 |
| `calc 'abc'` | `error: unexpected token` | 1 |
| `calc '2 +'` | `error: unexpected end of expression` | 1 |
| `calc '1 / 0'` | `error: division by zero` | 1 |
| `calc '1e999 * 2'` | `error: overflow` | 1 |
| `calc '2 + 3'` | *(nothing)* | 0 |

**Note on "unexpected token" dual origin:** the lexer emits `UnexpectedToken` for
characters it cannot tokenise. The parser should emit `UnexpectedToken` for a valid token
appearing in an unexpected position (e.g., `2 3` — extra token after complete parse).
Both map to the same message; the distinction lives in the enum variant source layer, not
in the user-visible string.

---

## 7. Acceptance Criteria Checklist

- [x] Every failure mode in the spec maps to exactly one error message format (§6 table)
- [x] Error messages are defined in a single `message()` function, making verbatim test
      assertions straightforward
- [x] Error type carries variant info; adding `(line, col)` payload per variant is
      additive — does not prevent future source-location info
- [x] stderr writing is centralized in `main` and isolated from lower layers

---

## 8. Follow-up Issues Recommended

None required for v0.1.0. Future issues to consider:

- **Add source-location (offset) to CalcError** — when named functions / variables are
  added, pointing at the offending token will be necessary for usability.
- **Distinct exit codes per error class** — only if a future spec revision mandates it;
  do not pre-empt.
