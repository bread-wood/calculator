# Low-Level Design — `parser` Module (v0.4.0)

**Milestone:** v0.4.0
**Module:** `parser` (`src/calc/parser.py`)
**Issue:** #184
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Scope

This document covers the low-level design of the `parser` module for the v0.4.0
milestone. The module consumes a token stream from `Lexer` and produces a typed
AST rooted at a `Program` node. v0.4.0 extends the parser to recognise
function-definition statements (`def name(params) = expr`) and introduce the
`FunctionDef` AST node and the `DEF` token branch in the statement dispatcher.

---

## 2. Data Structures

### 2.1 Existing AST Nodes (unchanged)

All existing node dataclasses remain in `parser.py` without modification.

```python
@dataclass
class Number:
    value: float

@dataclass
class BinaryOp:
    op: str
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str
    operand: ASTNode

@dataclass
class Name:
    name: str

@dataclass
class Call:
    func: str
    args: list[ASTNode]

ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

### 2.2 New: `FunctionDef` Dataclass

A new statement-level node added in v0.4.0, placed in `parser.py` alongside the
existing node definitions, after `Call` and before `Assignment`.

```python
@dataclass
class FunctionDef:
    name: str
    params: list[str]
    body: ASTNode
```

**Design rationale:**
- `name: str` — the function name, identical in position to `Assignment.name`.
- `params: list[str]` — bare identifier strings, not `ASTNode` objects. Parameters
  are syntactically distinct from expressions; storing strings avoids post-parse
  type inspection. An empty list represents a zero-parameter function.
- `body: ASTNode` — the fully-parsed expression tree. No source string is stored
  (research #156). The body is the canonical runtime representation; the evaluator
  operates on it directly without re-parsing.
- The dataclass mirrors `Assignment` in structure (`name + value/body`), following
  the established pattern from issue #113.
- `FunctionDef` is statement-level only; it cannot appear as a sub-expression.
  This matches `Assignment` precedent.
- Serialization-compatible by construction: all fields are either `str`,
  `list[str]`, or nested `ASTNode` dataclasses with primitive fields (research #156).

### 2.3 Updated `Statement` and `Program` Type Aliases

```python
# v0.3.x
Statement = Assignment | ASTNode

# v0.4.0
Statement = Assignment | FunctionDef | ASTNode

@dataclass
class Program:
    body: list[Statement]   # unchanged in structure
```

The `Program` dataclass itself requires no code change; its `body` field type
broadens automatically because `Statement` is a type alias.

### 2.4 `Parser` Internal State (unchanged)

```python
class Parser:
    _lexer: Lexer
    _current: Token          # token being examined now
    _lookahead: Token | None  # single-token lookahead buffer (lazy)
```

No new fields are added. The `_lookahead` field is already correct and fully
operational (research #158).

---

## 3. Grammar

The v0.4.0 grammar for the parser (EBNF):

```
program       ::= statement (';' statement)* ';'?
statement     ::= funcdef | assignment | expr
funcdef       ::= 'def' IDENT '(' param_list ')' '=' expr
assignment    ::= IDENT '=' expr
param_list    ::= ε | IDENT (',' IDENT)*
expr          ::= term (('+' | '-') term)*
term          ::= factor (('*' | '/') factor)*
factor        ::= unary
unary         ::= '-' unary | primary
primary       ::= NUMBER
              | '(' expr ')'
              | IDENT
              | IDENT '(' arg_list ')'
arg_list      ::= ε | expr (',' expr)*
```

The grammar is LL(1):
- `funcdef` is selected when `current.type == TokenType.DEF` — unambiguous, no
  lookahead required.
- `assignment` is selected when `current.type == IDENT` and
  `peek_next().type == EQUALS` — one-token lookahead, unchanged from v0.3.x.
- All other tokens fall through to `expr`.

---

## 4. Key Algorithms

### 4.1 `_parse_statement` Dispatch (updated)

Three-way branch on the current token type. LL(1) throughout.

```python
def _parse_statement(self) -> Statement:
    # Branch 1 (new): function definition
    if self._current.type == TokenType.DEF:
        return self._parse_funcdef()

    # Branch 2 (unchanged): variable assignment
    if self._current.type == TokenType.IDENT and \
            self._peek_next().type == TokenType.EQUALS:
        name = self._advance().value   # consume IDENT
        self._advance()               # consume EQUALS
        if self._current.type == TokenType.EOF:
            raise UnexpectedEnd()
        if self._current.type == TokenType.RPAREN:
            raise UnexpectedToken()
        value = self._parse_expr()
        return Assignment(name=name, value=value)

    # Branch 3 (unchanged): bare expression
    return self._parse_expr()
```

When `TokenType.DEF` is the current token, the parser commits to `_parse_funcdef`
immediately. No lookahead is consumed before committing (research #158).

### 4.2 `_parse_funcdef` (new)

Parses the `def name(params) = expr` form left-to-right. All tokens are consumed
in strict order; no backtracking.

```python
def _parse_funcdef(self) -> FunctionDef:
    self._advance()                              # consume DEF
    name = self._expect(TokenType.IDENT).value   # function name
    self._expect(TokenType.LPAREN)               # '('
    params = self._parse_param_list()            # ε | IDENT (',' IDENT)*
    self._expect(TokenType.RPAREN)               # ')'
    self._expect(TokenType.EQUALS)               # '=' body separator
    if self._current.type == TokenType.EOF:
        raise UnexpectedEnd()
    body = self._parse_expr()                    # expression tree
    return FunctionDef(name=name, params=params, body=body)
```

The `EQUALS` token after `)` is unambiguous: the parser has already committed to
`_parse_funcdef` via the `DEF` branch, so this `EQUALS` cannot be the assignment
operator (research #158, Q4).

### 4.3 `_parse_param_list` (new)

Parses zero or more comma-separated bare identifiers. Structurally mirrors
`_parse_arglist` but calls `_expect(TokenType.IDENT)` instead of `_parse_expr`,
returning `list[str]` rather than `list[ASTNode]`.

```python
def _parse_param_list(self) -> list[str]:
    params: list[str] = []
    if self._current.type == TokenType.RPAREN:
        return params                              # def f() = expr
    params.append(self._expect(TokenType.IDENT).value)
    while self._current.type == TokenType.COMMA:
        self._advance()                            # consume ','
        params.append(self._expect(TokenType.IDENT).value)
    return params
```

`_parse_arglist` cannot be reused: it calls `_parse_expr()` per element and
returns `list[ASTNode]`. Reuse would accept syntactically invalid inputs such as
`def f(x + 1) = x` and return expression nodes instead of name strings, forcing
an awkward post-parse narrowing (research #158, Q3).

### 4.4 `_parse_arglist` (unchanged)

The existing method is unchanged. It is called from `_parse_primary` when an
`IDENT` is immediately followed by `LPAREN`, covering both built-in and
user-defined function calls.

### 4.5 `_peek_next` and `_advance` (unchanged)

The single-token lookahead mechanism is correct and complete. `_peek_next()` is
used only in the `_parse_statement` assignment branch. `_parse_funcdef` never
calls `_peek_next()`; it consumes tokens strictly left-to-right.

---

## 5. Public API / Interfaces

### 5.1 Module-level exports

The following names are exported from `parser.py` (by import convention; no
`__all__` is used):

| Name | Kind | Status |
|---|---|---|
| `Number` | dataclass | unchanged |
| `BinaryOp` | dataclass | unchanged |
| `UnaryOp` | dataclass | unchanged |
| `Name` | dataclass | unchanged |
| `Call` | dataclass | unchanged |
| `ASTNode` | type alias | unchanged |
| `Assignment` | dataclass | unchanged |
| `FunctionDef` | dataclass | **new** |
| `Program` | dataclass | unchanged |
| `Statement` | type alias | **extended** (`+= FunctionDef`) |
| `Parser` | class | updated (new methods) |

### 5.2 `Parser` public method

```python
class Parser:
    def __init__(self, lexer: Lexer) -> None: ...
    def parse_program(self) -> Program: ...
```

`parse_program()` is the sole public method. Its signature and return type are
unchanged. The new `FunctionDef` nodes appear inside `Program.body` alongside
`Assignment` and expression nodes.

### 5.3 `Parser` private methods

| Method | Signature | Status |
|---|---|---|
| `_parse_statement` | `() -> Statement` | updated |
| `_parse_funcdef` | `() -> FunctionDef` | **new** |
| `_parse_param_list` | `() -> list[str]` | **new** |
| `_parse_arglist` | `() -> list[ASTNode]` | unchanged |
| `_parse_expr` | `() -> ASTNode` | unchanged |
| `_parse_term` | `() -> ASTNode` | unchanged |
| `_parse_factor` | `() -> ASTNode` | unchanged |
| `_parse_unary` | `() -> ASTNode` | unchanged |
| `_parse_primary` | `() -> ASTNode` | unchanged |
| `_peek_next` | `() -> Token` | unchanged |
| `_advance` | `() -> Token` | unchanged |
| `_match` | `(*types: TokenType) -> bool` | unchanged |
| `_expect` | `(type: TokenType) -> Token` | unchanged |

### 5.4 File placement

All new dataclasses (`FunctionDef`) and updated type aliases (`Statement`) are
defined in `src/calc/parser.py`. No separate `ast.py` is introduced (HLD open
question #2 resolved: keep everything in `parser.py` for consistency with the
existing node definitions and to avoid a new import surface).

### 5.5 Dependency on `lexer`

The parser imports `TokenType.DEF` from `calc.lexer`. No other new imports are
required. `TokenType.DEF` is added to the lexer module per research #153 and the
lexer LLD; the parser depends on it being present.

---

## 6. Error Handling

The parser raises errors from `calc.errors`. No new error classes are introduced
in the parser module. All error conditions map to existing classes.

### 6.1 Error table

| Condition | Token state | Error raised |
|---|---|---|
| `def` not followed by `IDENT` (e.g. `def 5(x) = x`) | current is not `IDENT` inside `_expect(IDENT)` | `UnexpectedToken` |
| `def name` not followed by `(` | current is not `LPAREN` inside `_expect(LPAREN)` | `UnexpectedToken` or `UnexpectedEnd` |
| Non-`IDENT` token in parameter list (e.g. `def f(x+1)`) | current is not `IDENT` inside `_expect(IDENT)` in `_parse_param_list` | `UnexpectedToken` |
| Missing `)` after parameter list | current is not `RPAREN` inside `_expect(RPAREN)` | `UnexpectedToken` or `UnexpectedEnd` |
| Missing `=` after `)` | current is not `EQUALS` inside `_expect(EQUALS)` | `UnexpectedToken` or `UnexpectedEnd` |
| Empty body after `=` (EOF) | `current.type == TokenType.EOF` before `_parse_expr()` | `UnexpectedEnd` |
| `def` at a non-statement position | Cannot occur — `DEF` is not a valid primary; any `DEF` token starts `_parse_statement` | — |

### 6.2 `_expect` behaviour (existing)

`_expect(type)` raises `UnexpectedEnd` when `current.type == EOF`, and
`UnexpectedToken` for any other mismatch. This behaviour is unchanged and covers
all the error cases in `_parse_funcdef` and `_parse_param_list` without additional
logic.

### 6.3 No parser-level semantic validation

The parser does not check:
- Whether the function name conflicts with a built-in or an existing user function.
- Whether parameters are referenced in the body.
- Whether the body contains forward references.

All semantic validation is the evaluator's responsibility, performed when
`execute_statement(FunctionDef(...), ...)` is called. The parser is purely
syntactic.

---

## 7. Test Strategy

Tests live in `tests/test_parser.py`. A new `# v0.4.0 — user-defined functions`
block is appended to the existing file (research #159). No new test file is created.

### 7.1 Test cases

#### Success cases

| Test name | Input | Expected `Program.body[0]` |
|---|---|---|
| `test_funcdef_no_params` | `"def f() = 1"` | `FunctionDef(name="f", params=[], body=Number(1.0))` |
| `test_funcdef_one_param` | `"def f(x) = x"` | `FunctionDef(name="f", params=["x"], body=Name("x"))` |
| `test_funcdef_multi_params` | `"def f(x, y) = x + y"` | `FunctionDef(name="f", params=["x", "y"], body=BinaryOp("+", Name("x"), Name("y")))` |
| `test_funcdef_body_expression` | `"def g(x) = x * 2 + 1"` | `FunctionDef` with `BinaryOp("+", BinaryOp("*", Name("x"), Number(2.0)), Number(1.0))` |
| `test_funcdef_followed_by_call` | `"def f(x) = x; f(3)"` | `body` has two nodes: `FunctionDef`, then `Call(func="f", args=[Number(3.0)])` |
| `test_call_in_expression` | `"f(1) + 2"` | `BinaryOp("+", Call("f", [Number(1.0)]), Number(2.0))` |
| `test_funcdef_body_uses_call` | `"def h(x) = sqrt(x)"` | `FunctionDef` with `body=Call("sqrt", [Name("x")])` |

#### Error cases

| Test name | Input | Expected exception |
|---|---|---|
| `test_funcdef_missing_name` | `"def (x) = 1"` | `UnexpectedToken` |
| `test_funcdef_missing_lparen` | `"def f x) = 1"` | `UnexpectedToken` |
| `test_funcdef_non_ident_param` | `"def f(x + 1) = x"` | `UnexpectedToken` |
| `test_funcdef_missing_rparen` | `"def f(x = 1"` | `UnexpectedToken` |
| `test_funcdef_missing_equals` | `"def f(x) 1"` | `UnexpectedToken` |
| `test_funcdef_empty_body` | `"def f(x) ="` | `UnexpectedEnd` |

### 7.2 Test approach

- All tests call `Parser(Lexer(source)).parse_program()` directly; no evaluator involvement.
- Node equality is verified via dataclass `==` (automatic from `@dataclass`).
- Error cases use `pytest.raises(ExpectedExceptionType)`.
- `@pytest.mark.parametrize` is appropriate for the success cases that share
  identical assertion structure (input → `Program.body[0]` node shape). Error
  cases may use either `parametrize` or individual named functions; individual
  named functions are preferred when the expected exception type varies.

### 7.3 Regression

No existing `test_parser.py` tests require modification. The new `DEF` token does
not affect any existing token sequence (the v0.3.x test suite uses no identifier
named `def`; confirmed in research #158).

---

## 8. Implementation Checklist

The following concrete changes are required in `src/calc/parser.py`:

1. Add `FunctionDef` dataclass after `Call`, before `Assignment`.
2. Update `Statement` type alias from `Assignment | ASTNode` to
   `Assignment | FunctionDef | ASTNode`.
3. Add `DEF` branch at the top of `_parse_statement`.
4. Add `_parse_funcdef()` method.
5. Add `_parse_param_list()` method.
6. No changes to any other method, field, or import beyond `TokenType.DEF`
   (which is added by the lexer module; the parser imports `TokenType` already).

All other parser methods, the `Parser.__init__`, and `parse_program` are
unchanged.

---

## 9. Open Questions Resolved

This section records the HLD open questions assigned to the parser LLD.

| HLD Open Question | Resolution |
|---|---|
| Should `FunctionDef` live in `parser.py` or a separate `ast.py`? | `parser.py` — keeps all node definitions co-located; avoids a new import surface; consistent with existing pattern. |
| Exact error when `def` is followed by a non-`IDENT` token (e.g. `def 5(x) = x`)? | `_expect(TokenType.IDENT)` raises `UnexpectedToken` (or `UnexpectedEnd` if EOF). No special-casing needed; `_expect` covers both. |
