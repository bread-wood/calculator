# Research: Comma Parsing for Multi-Argument Functions (pow, atan2)

**Issue:** #77
**Date:** 2026-03-04
**Milestone:** v0.2.0

---

## Summary

- **Comma lexing:** Add `TokenType.COMMA` to the lexer (`_SINGLE_CHAR[","]`). No `UNKNOWN` fallthrough.
- **Arglist parsing:** Add `_parse_arglist` helper to `Parser`; it calls `_parse_expr` per argument, stopping at `)` and `,`. Expression parsing already terminates cleanly on both tokens.
- **Parser strategy:** Recursive descent. No restructuring needed; one new branch in `_parse_primary` and one new helper method suffice.
- **Arity checking:** At eval time, using the `Call.func` name already carried by the AST for targeted error messages.
- **Nested calls:** `pow(atan2(1,1), 2)` parses correctly because `_parse_arglist` delegates to `_parse_expr`, which recurses into `_parse_primary` → `_parse_arglist` for the inner call.

---

## 1. Q1 — Is comma already a token in the v0.1.x lexer?

**No.** The v0.1.x `lexer.py` `TokenType` enum contains:

```
NUMBER, PLUS, MINUS, STAR, SLASH, LPAREN, RPAREN, EOF, UNKNOWN
```

The `_SINGLE_CHAR` dispatch table covers `+`, `-`, `*`, `/`, `(`, `)`. Any unrecognised character — including `,` — falls through to:

```python
return Token(TokenType.UNKNOWN, ch)
```

A bare `,` currently produces `Token(UNKNOWN, ",")`.

**Required change:** Add `COMMA = auto()` to `TokenType` and `",": TokenType.COMMA` to `_SINGLE_CHAR`. Research #65 analysed this in detail and concluded that a first-class `TokenType.COMMA` is required (not `UNKNOWN`+value inspection) to keep lexer–parser coupling minimal and consistent with the existing design where every syntactically meaningful character has its own type.

**No existing test is affected.** The two `UNKNOWN` tests use `@` and `$`; neither is `,`.

---

## 2. Q2 — How does the parser handle the arglist production, and does expression parsing terminate cleanly on `)` and `,`?

**Arglist production** (from research #53, confirmed against current source):

```python
def _parse_arglist(self) -> list[ASTNode]:
    args: list[ASTNode] = []
    if self._current.type == TokenType.RPAREN:
        return args          # zero-arg call: f()
    args.append(self._parse_expr())
    while self._current.type == TokenType.COMMA:
        self._advance()
        args.append(self._parse_expr())
    return args
```

**Does `_parse_expr` terminate cleanly on `)` and `,`?**

Yes. Tracing the grammar:

| Method | Loop condition | Terminates on `)` | Terminates on `,` |
|---|---|---|---|
| `_parse_expr` | `PLUS` or `MINUS` | yes | yes |
| `_parse_term` | `STAR` or `SLASH` | yes | yes |
| `_parse_factor` | delegates to `_parse_unary` | — | — |
| `_parse_unary` | `MINUS` (right-recursive) | yes | yes |
| `_parse_primary` | no loop | yes (returns on `RPAREN`) | yes (raises `UnexpectedToken`) |

Neither `)` nor `,` is consumed by any expression production. Each call to `_parse_expr` inside `_parse_arglist` stops as soon as it encounters a `,` or `)`, leaving the token for the caller to dispatch on.

**Nested multi-arg calls — `pow(atan2(1,1), 2)`:**

1. Outer `_parse_arglist` calls `_parse_expr`.
2. `_parse_expr` → `_parse_primary` sees `atan2` (IDENT) followed by `(`, enters inner `_parse_arglist`.
3. Inner `_parse_arglist` consumes `1`, `,`, `1`, stops at `)`.
4. Inner call returns a `Call(func="atan2", args=[...])` node.
5. Outer `_parse_expr` returns that node.
6. Outer `_parse_arglist` sees `,`, advances, calls `_parse_expr` again → produces `Number(2)`.
7. Outer `_parse_arglist` sees `)`, stops and returns two-element list.

No ambiguity; each comma is unambiguously assigned to the innermost open arglist because `_parse_expr` terminates on `,`.

---

## 3. Q3 — Does the v0.1.x parser use top-down recursive descent or a table-driven approach?

**Recursive descent.** `parser.py` is a hand-written recursive descent parser:

- `_parse_expr` → `_parse_term` → `_parse_factor` → `_parse_unary` → `_parse_primary`
- Each method calls the next-lower precedence level; no parse table, no operator precedence table lookup.

**Extension required:** Add one new branch inside `_parse_primary` (IDENT → function call or bare name) and one new helper `_parse_arglist`. Zero modifications to `_parse_expr`, `_parse_term`, `_parse_factor`, or `_parse_unary`.

```python
# In _parse_primary, before the final raise UnexpectedToken():
if self._current.type == TokenType.IDENT:
    name = self._advance().value
    if self._current.type == TokenType.LPAREN:
        self._advance()
        args = self._parse_arglist()
        self._expect(TokenType.RPAREN)
        return Call(func=name, args=args)
    return Name(name=name)
```

No grammar restructuring, no precedence table additions.

---

## 4. Q4 — Arity mismatch: parse time or eval time?

**Eval time**, with the function name available from the AST `Call` node.

**Reasoning:**

1. The parser does not maintain a function registry; it does not know at parse time which names are valid or what their arities are. The parser's job is to produce a structurally valid AST from the token stream.

2. The `Call` AST node (from research #53) carries both `func: str` and `args: list[ASTNode]`:

   ```python
   @dataclass
   class Call:
       func: str
       args: list[ASTNode]
   ```

   The evaluator receives `Call(func="pow", args=[...])` and can check `len(args)` against the expected arity for `"pow"`. The function name is present, so error messages can reference it directly:

   ```
   error: pow() takes 2 arguments, got 1
   ```

3. Checking at parse time would require the parser to import or be passed the function dispatch table, coupling parser to evaluator. That coupling is undesirable given the existing clean layering (lexer → parser → evaluator).

4. The existing `errors.py` model uses subclass-per-error. A new `ArityError` subclass in `errors.py` (or a parameterised variant, as researched in #55) can carry the function name and counts needed for a clear message.

**Conclusion:** Arity is checked in the evaluator. The parser validates structural correctness (balanced parens, valid expression per argument); the evaluator validates semantic correctness (correct number of arguments for each named function).

---

## 5. Minimal Change Summary

### `lexer.py` — 2 lines

```python
# TokenType — add after RPAREN:
COMMA = auto()

# _SINGLE_CHAR — add:
",": TokenType.COMMA,
```

### `parser.py` — new dataclasses + one branch + one helper

```python
# New AST nodes (alongside Number, BinaryOp, UnaryOp):
@dataclass
class Name:
    name: str

@dataclass
class Call:
    func: str
    args: list[ASTNode]

ASTNode = Number | BinaryOp | UnaryOp | Name | Call

# _parse_primary — new branch before raise UnexpectedToken():
if self._current.type == TokenType.IDENT:
    name = self._advance().value
    if self._current.type == TokenType.LPAREN:
        self._advance()
        args = self._parse_arglist()
        self._expect(TokenType.RPAREN)
        return Call(func=name, args=args)
    return Name(name=name)

# New helper:
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

### `evaluator.py` — new branches for `Name` and `Call`

Arity check inside the `Call` branch:

```python
if isinstance(node, Call):
    fn_entry = FUNCTIONS.get(node.func)
    if fn_entry is None:
        raise UnknownFunction(node.func)
    expected_arity, fn = fn_entry
    if len(node.args) != expected_arity:
        raise ArityError(node.func, expected_arity, len(node.args))
    evaluated = [evaluate(a) for a in node.args]
    result = fn(*evaluated)
    _check_overflow(result)
    return result
```

---

## 6. Verdict

| Question | Answer |
|---|---|
| Comma in v0.1.x lexer? | No — add `TokenType.COMMA` to `TokenType` and `_SINGLE_CHAR` |
| Arglist parsing approach | `_parse_arglist` helper calling `_parse_expr`; terminates cleanly on `)` and `,` |
| Parser strategy | Recursive descent; one new branch in `_parse_primary`, one new helper |
| Arity check location | Eval time; `Call.func` name available for targeted error messages |
| Nested calls | Handled automatically by recursive `_parse_expr` calls inside `_parse_arglist` |
