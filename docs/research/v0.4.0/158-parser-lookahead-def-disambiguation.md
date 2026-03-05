# Research: Parser Lookahead Requirements for `def` Statement Disambiguation

**Issue:** #158
**Date:** 2026-03-05
**Milestone:** v0.4.0

---

## Summary

**Recommendation: Use `DEF` as a reserved token (per issue #153 recommendation).** With `DEF` as a distinct `TokenType`, `_parse_statement` needs **zero additional lookahead** for function-definition dispatch — a single `current.type == TokenType.DEF` check is sufficient. The existing `_lookahead` field and `_peek_next()` mechanism are correct and complete; no new lookahead infrastructure is needed. A dedicated `_parse_funcdef()` and `_parse_param_list()` must be added; the existing `_parse_arglist()` cannot be directly reused because parameters are bare identifiers, not arbitrary expressions.

---

## Question 1 — Reserved token vs contextual IDENT: lookahead impact

Issue #153 recommends adding `DEF = auto()` to `TokenType` and having the lexer emit `DEF` for the string `"def"`. This research assumes that recommendation is accepted.

### With `DEF` as a reserved token (recommended)

`_parse_statement` dispatches on `current.type`:

```python
def _parse_statement(self) -> Statement:
    if self._current.type == TokenType.DEF:
        return self._parse_funcdef()                          # <-- new branch; no lookahead needed
    if self._current.type == TokenType.IDENT and self._peek_next().type == TokenType.EQUALS:
        # assignment — unchanged
        ...
    return self._parse_expr()                                 # unchanged
```

The `DEF` token is unambiguous at position 0. No lookahead is consumed before committing to `_parse_funcdef`. The existing one-token lookahead for assignment (`_peek_next()`) is completely unchanged.

### With contextual IDENT (not recommended, for completeness)

If `def` remained `IDENT("def")`, `_parse_statement` would need to distinguish:

| Input            | Token sequence                          | Statement type |
|------------------|-----------------------------------------|----------------|
| `def f(x) = ...` | IDENT("def") IDENT("f") LPAREN ...      | FuncDef        |
| `def = 5`        | IDENT("def") EQUALS NUMBER              | Assignment     |
| `def + 1`        | IDENT("def") PLUS NUMBER                | Expression     |

Only `_peek_next()` (one-token lookahead) would be required:
- `next == IDENT` → funcdef
- `next == EQUALS` → assignment (with `def` as the variable name)
- anything else → expression

This is technically still LL(1), but the decision logic is muddled: `def` is simultaneously a possible variable name, a possible expression-start, and a keyword. The reserved-token design avoids this entirely.

**Verdict:** With the recommended `DEF` token, `_parse_statement` requires **no additional lookahead depth** beyond what already exists.

---

## Question 2 — Legacy `def` as a bare identifier

The v0.3.x test suite contains **zero uses** of `def` as a variable name or identifier (confirmed in issue #153 research). The full identifier inventory from the test files is: `x`, `y`, `z`, `a`, `b`, `sqrt`, `pi`, `e`, `atan2`, `_var`, `x1`. There is no regression concern.

After the `DEF` token is introduced:
- `def = 5` — lexer emits `DEF EQUALS NUMBER`; parser hits `_parse_funcdef` and raises `UnexpectedToken` (no IDENT follows `DEF`). This is the correct rejection.
- `define = 5` — `define` is not in the keyword table; lexer emits `IDENT("define")`; parser handles it as an ordinary assignment. No impact.

---

## Question 3 — Parsing the parameter list

The grammar form is:

```
def IDENT '(' param_list ')' '=' expr
param_list ::= ε | IDENT (',' IDENT)*
```

Parameters are **bare identifiers**, not arbitrary expressions. The existing `_parse_arglist()` (`parser.py:158-166`) parses comma-separated expressions by calling `_parse_expr()`. Reusing it for parameters would:

1. Accept syntactically invalid inputs like `def f(x + 1) = x` without error.
2. Return `ASTNode` objects instead of parameter name strings, forcing an awkward post-parse type check.

**A dedicated `_parse_param_list()` is required.** It should mirror `_parse_arglist()` structurally but call `_expect(TokenType.IDENT)` for each item:

```python
def _parse_param_list(self) -> list[str]:
    params: list[str] = []
    if self._current.type == TokenType.RPAREN:
        return params                              # def f() = expr  (zero params)
    params.append(self._expect(TokenType.IDENT).value)
    while self._current.type == TokenType.COMMA:
        self._advance()                            # consume ','
        params.append(self._expect(TokenType.IDENT).value)
    return params
```

The three forms — zero, one, and multiple parameters — are all handled by this single method without any additional lookahead.

---

## Question 4 — EQUALS sign ambiguity after `)`

After `def f(x, y)`, the parser sees an `EQUALS` token. The same `EQUALS` token type appears in variable assignment (`name = expr`). Is there ambiguity?

**No.** The dispatch has already committed to `_parse_funcdef()` before consuming any tokens past `DEF`. Inside `_parse_funcdef`, the token sequence is deterministic:

```
DEF   IDENT   LPAREN   param_list   RPAREN   EQUALS   expr
 ^consumed      ^consumed            ^consumed  ^must see here
```

At the point where `EQUALS` is expected, the parser has already consumed `DEF`, the function name, `(`, the parameter list, and `)`. There is no code path in which the same `EQUALS` could be the assignment operator, because assignment requires the current token to be `IDENT` (not `DEF`) at the top of `_parse_statement`. The `EQUALS` inside `_parse_funcdef` is unambiguously the body separator.

---

## Question 5 — The `_lookahead` field

`_lookahead: Token | None` is declared at `parser.py:59` and is used correctly by `_peek_next()` (`parser.py:84-87`) and `_advance()` (`parser.py:89-96`):

- `_peek_next()` populates `_lookahead` lazily from the lexer.
- `_advance()` consumes `_lookahead` first if it is set, then clears it.

This is a standard single-token lookahead buffer. It is **not** incomplete or partially implemented. The field simply appears unused when viewed from `_parse_funcdef` because that method will not need `_peek_next()` at all — it can parse the `def` form entirely by consuming tokens left-to-right.

The one place `_peek_next()` continues to be used is the assignment check in `_parse_statement` (`parser.py:73`), which is unchanged.

**Conclusion:** The `_lookahead` field is correct and fully operational. No changes to the lookahead infrastructure are needed.

---

## Recommended `_parse_statement` Dispatch Logic

```python
def _parse_statement(self) -> Statement:
    # Branch 1: function definition — requires DEF token (issue #153)
    if self._current.type == TokenType.DEF:
        return self._parse_funcdef()

    # Branch 2: variable assignment — unchanged from v0.3.x
    if self._current.type == TokenType.IDENT and self._peek_next().type == TokenType.EQUALS:
        name = self._advance().value   # consume IDENT
        self._advance()               # consume EQUALS
        if self._current.type == TokenType.EOF:
            raise UnexpectedEnd()
        if self._current.type == TokenType.RPAREN:
            raise UnexpectedToken()
        value = self._parse_expr()
        return Assignment(name=name, value=value)

    # Branch 3: bare expression — unchanged from v0.3.x
    return self._parse_expr()
```

The three-way branch is **LL(1)**: each branch is selected by the type of the current token alone. No two-token lookahead is required.

---

## Recommended `_parse_funcdef` Skeleton

```python
def _parse_funcdef(self) -> FuncDef:
    self._advance()                              # consume DEF
    name = self._expect(TokenType.IDENT).value   # function name
    self._expect(TokenType.LPAREN)
    params = self._parse_param_list()
    self._expect(TokenType.RPAREN)
    self._expect(TokenType.EQUALS)               # body separator
    if self._current.type == TokenType.EOF:
        raise UnexpectedEnd()
    body = self._parse_expr()
    return FuncDef(name=name, params=params, body=body)
```

`FuncDef` is a new AST node (not currently in `parser.py`) that will need to be defined alongside this method. Its form is straightforward:

```python
@dataclass
class FuncDef:
    name: str
    params: list[str]
    body: ASTNode
```

---

## Implementation Surface

| File | Change |
|------|--------|
| `src/calc/lexer.py` | Add `DEF` to `TokenType`; add keyword table; update `_scan_ident` (see issue #153) |
| `src/calc/parser.py` | Add `FuncDef` dataclass; update `Statement` type alias; add `DEF` branch in `_parse_statement`; add `_parse_funcdef()` and `_parse_param_list()` |
| `tests/test_parser.py` | New tests for `def f() = expr`, `def f(x) = expr`, `def f(x, y) = expr`, and error cases |

---

## Decisions

| Question | Decision |
|----------|----------|
| DEF reserved token required? | **Yes** — per issue #153; zero regression risk; simplifies all dispatch |
| Additional lookahead depth needed? | **No** — LL(1) is sufficient; `_peek_next()` unchanged; `_lookahead` field is already correct |
| Reuse `_parse_arglist` for parameters? | **No** — params are bare IDENTs; a dedicated `_parse_param_list` avoids accepting expression syntax |
| EQUALS ambiguity? | **None** — context inside `_parse_funcdef` is unambiguous; EQUALS is always the body separator |
| `_lookahead` field safe to use? | **Yes** — fully implemented; used by `_peek_next()` / `_advance()` today |

---

## Follow-up Issues Spawned

None. All open questions are resolved. The implementation can proceed directly from this document and the lexer change described in issue #153.
