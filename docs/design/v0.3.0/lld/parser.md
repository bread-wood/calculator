# Low-Level Design — Parser Module (v0.3.0)

**Module:** `parser`
**File:** `src/calc/parser.py`
**Milestone:** v0.3.0 (Variables)
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Responsibility

The parser consumes a token stream from `Lexer` and produces a typed Abstract Syntax Tree rooted at a `Program` node. v0.3.0 extends the v0.2.0 single-expression parser to handle multi-statement programs separated by semicolons and introduces variable assignment as a new statement form. The parser enforces grammar rules, operator precedence, and associativity. It does **not** resolve variable names, validate constants, perform evaluation, or write to stdout/stderr.

**Scope boundary:** The parser does not know which names are read-only constants or which names are currently bound. It emits an `Assignment` node for any `IDENT '=' expr` statement and a `Name` node for any bare identifier reference. Semantic validation (undefined variable, constant reassignment) is the evaluator's responsibility.

---

## 2. Public Interface

### 2.1 AST Node Types

All node types are `dataclass` instances. Structural equality (`==`) is provided by the dataclass machinery. The `ASTNode` union type alias is **unchanged** from v0.2.0 and covers only expression-level nodes. Two new top-level nodes (`Assignment`, `Program`) and one new type alias (`Statement`) are added.

```python
from __future__ import annotations
from dataclasses import dataclass

# --- expression-level nodes (unchanged from v0.2.0) ---

@dataclass
class Number:
    value: float           # parsed float literal

@dataclass
class BinaryOp:
    op: str                # one of: '+', '-', '*', '/'
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str                # only '-' in v0.3.0
    operand: ASTNode

@dataclass
class Name:
    name: str              # raw lexeme, e.g. "pi", "x"

@dataclass
class Call:
    func: str              # function name lexeme
    args: list[ASTNode]    # positional arguments

ASTNode = Number | BinaryOp | UnaryOp | Name | Call   # unchanged

# --- statement-level nodes (new v0.3.0) ---

@dataclass
class Assignment:
    name: str              # target variable name (lhs of '=')
    value: ASTNode         # rhs expression; no spans in v0.3.0

@dataclass
class Program:
    body: list[Statement]  # ordered list of statements

Statement = Assignment | ASTNode   # statement-level union
```

**Rationale — `Assignment` not in `ASTNode`:** Assignment is only valid at statement level; embedding it in `ASTNode` would allow the type system to represent `BinaryOp(left=Assignment(...), right=...)`, which is semantically impossible. A separate `Statement` union keeps the type precise and eliminates dead states (research #113 Q3).

**Rationale — `Program` wrapper vs. plain `list`:** A `Program` node keeps the parser's return type a single structured value, making the AST uniformly traversable. Callers receive one object and iterate `program.body`; no special-case `isinstance(result, list)` check is needed. It also aligns with the v0.4.0 requirement for function bodies as statement lists (research #113 Q2).

**Rationale — no position/span on `Assignment`:** No other node type carries position information, and the lexer does not expose token offsets. Adding spans to `Assignment` alone would be inconsistent. Span tracking is deferred to a future cross-cutting issue (research #113 Q1).

### 2.2 Parser Class

```python
class Parser:
    def __init__(self, lexer: Lexer) -> None: ...
    def parse_program(self) -> Program: ...
```

**`Parser(lexer: Lexer)`** — constructs a parser, pre-fetches the first token into `_current`, and initialises `_lookahead` to `None`.

**`Parser.parse_program() -> Program`** — entry point replacing `parse()`. Parses one or more semicolon-delimited statements (trailing semicolon accepted), wraps the resulting list in a `Program` node, asserts `_current.type == TokenType.EOF`, and returns the root node. Raises `UnexpectedToken` or `UnexpectedEnd` on grammar violations.

**Note on `parse()` removal:** The old `parse() -> ASTNode` method is removed entirely. There is exactly one call-site (`__main__.py`), which is updated in the same PR. Keeping the old method as dead code would be misleading (research #110 Q4).

### 2.3 Error Types Raised

| Error | Condition |
|---|---|
| `UnexpectedToken` | Wrong token where an operand, closing paren, or `=` rhs is expected |
| `UnexpectedEnd` | EOF reached before a statement or closing `)` is complete |

No new error types are raised by the parser in v0.3.0. Semantic errors (`UndefinedVariable`, `ConstantReassignment`) are raised by the evaluator, not the parser.

---

## 3. Data Structures

### 3.1 Parser State

```python
class Parser:
    _lexer:     Lexer
    _current:   Token        # next unconsumed token
    _lookahead: Token | None # lazily-filled second lookahead slot
```

v0.3.0 adds a `_lookahead` slot (initialised to `None`) to support the two-token window needed in `_parse_statement`. The slot is filled on demand by `_peek_next()` and consumed by `_advance()`. All existing call-sites that use only `_current` and `_advance()` are unaffected (research #110 Q1 Option A).

---

## 4. Grammar

v0.3.0 adds a program and statement production layer on top of the unchanged expression grammar:

```
program    = statement { ';' statement } [ ';' ]
statement  = IDENT '=' expression       # Assignment
           | expression                 # expression statement

expr       = term ( ('+' | '-') term )*
term       = factor ( ('*' | '/') factor )*
factor     = unary
unary      = '-' unary | primary
primary    = NUMBER
           | '(' expr ')'
           | IDENT '(' arglist ')'
           | IDENT

arglist    = ε
           | expr ( ',' expr )*
```

All expression-level productions are unchanged from v0.2.0.

**Grammar properties:**
- The `statement` production requires a 2-token lookahead: `IDENT` alone is ambiguous between `IDENT '=' expr` (Assignment) and `IDENT ...` (expression starting with a Name). Checking the token *after* `IDENT` — via `_peek_next()` — resolves the ambiguity without backtracking.
- Trailing semicolons are accepted (`[ ';' ]` at the end of `program`). This is consistent with shell tool conventions and prevents confusing errors for users who naturally type trailing semicolons (research #110 Q3).
- A program must contain at least one statement; the empty string is rejected by `_parse_statement` raising `UnexpectedEnd`.

---

## 5. Key Algorithms and Logic

### 5.1 `_peek_next` — Lazy Second Lookahead

```python
def _peek_next(self) -> Token:
    if self._lookahead is None:
        self._lookahead = self._lexer.next_token()
    return self._lookahead
```

Called only from `_parse_statement` when `_current` is `IDENT`. Fills `_lookahead` at most once per use. The slot is drained by the next `_advance()` call.

### 5.2 `_advance` — Updated to Drain Lookahead

```python
def _advance(self) -> Token:
    previous = self._current
    if self._lookahead is not None:
        self._current = self._lookahead
        self._lookahead = None
    else:
        self._current = self._lexer.next_token()
    return previous
```

If a lookahead token was pre-fetched, it becomes the new `_current` without calling `next_token()` again. This is the only change to the token-advancement machinery; all other call-sites are unaffected.

### 5.3 `parse_program` — Program Entry Point

```python
def parse_program(self) -> Program:
    statements: list[Statement] = [self._parse_statement()]
    while self._match(TokenType.SEMICOLON):
        if self._current.type == TokenType.EOF:
            break          # trailing semicolon — stop
        statements.append(self._parse_statement())
    if self._current.type != TokenType.EOF:
        raise UnexpectedToken()
    return Program(body=statements)
```

**Flow:**

```
parse_program
    │
    ├─ parse first statement
    │
    ├─ loop: while SEMICOLON consumed
    │       ├─ if EOF → break (trailing semicolon accepted)
    │       └─ parse next statement
    │
    ├─ if not EOF → UnexpectedToken
    │
    └─ return Program(body=[...])
```

### 5.4 `_parse_statement` — Statement Dispatch

```python
def _parse_statement(self) -> Statement:
    if (self._current.type == TokenType.IDENT
            and self._peek_next().type == TokenType.EQUALS):
        name = self._advance().value   # consume IDENT
        self._advance()                # consume '='
        value = self._parse_expr()
        return Assignment(name=name, value=value)
    return self._parse_expr()
```

**Decision point:**

```
_parse_statement
    │
    ├─ current=IDENT AND next=EQUALS
    │       → consume IDENT + EQUALS
    │       → _parse_expr() for rhs
    │       → Assignment(name, value)
    │
    └─ anything else
            → _parse_expr()   (returns an ASTNode directly as Statement)
```

**Why not treat `=` as a lowest-precedence operator:** Adding `=` inside `_parse_expr` would make assignment syntactically valid inside any expression (e.g., `(x=5)+1`), allow chains like `x = y = 5`, and produce misleading error messages at the wrong layer. A dedicated `_parse_statement` keeps assignment strictly at statement level and makes future statement types (`let`, `print`, `def`) straightforward one-line additions (research #110 Q2).

### 5.5 Trailing Semicolon Policy

The trailing-semicolon policy is encoded in exactly one place: the `if self._current.type == TokenType.EOF: break` guard inside `parse_program`'s loop. Tightening the policy later (to reject trailing semicolons) requires removing that single guard.

### 5.6 Expression Grammar (unchanged from v0.2.0)

`_parse_expr`, `_parse_term`, `_parse_factor`, `_parse_unary`, `_parse_primary`, and `_parse_arglist` are unchanged. Their behaviour, edge cases, and rationale are fully documented in the v0.2.0 LLD.

---

## 6. Internal Structure

### 6.1 File Layout (`src/calc/parser.py`)

```
imports
  from __future__ import annotations
  from dataclasses import dataclass
  from calc.errors import UnexpectedEnd, UnexpectedToken
  from calc.lexer import Lexer, Token, TokenType

AST dataclasses — expression level (unchanged)
  Number, BinaryOp, UnaryOp, Name, Call

ASTNode type alias (unchanged)
  ASTNode = Number | BinaryOp | UnaryOp | Name | Call

AST dataclasses — statement level (new v0.3.0)
  Assignment
  Program

Statement type alias (new v0.3.0)
  Statement = Assignment | ASTNode

Parser class
  __init__                        (adds _lookahead slot)
  parse_program                   (new; replaces parse)
  _advance                        (updated: drains _lookahead)
  _peek_next                      (new)
  _match                          (unchanged)
  _expect                         (unchanged)
  _parse_statement                (new)
  _parse_expr                     (unchanged)
  _parse_term                     (unchanged)
  _parse_factor                   (unchanged)
  _parse_unary                    (unchanged)
  _parse_primary                  (unchanged)
  _parse_arglist                  (unchanged)
```

No new files are introduced. All new and existing types remain in `parser.py`. Moving AST nodes to a separate `ast.py` is deferred; the module is small enough that co-location is not a maintenance burden in v0.3.0 (HLD open question 1 resolved: keep in `parser.py`).

### 6.2 Private Helpers

| Helper | Change | Purpose |
|---|---|---|
| `_advance()` | Updated | Consume current token; promote `_lookahead` if set; load next from lexer otherwise |
| `_peek_next()` | New | Lazily fetch and cache the token after `_current`; used only in `_parse_statement` |
| `_match(*types)` | Unchanged | Consume and return `True` iff current token is one of `types`; used in operator loops and `parse_program` |
| `_expect(type)` | Unchanged | Consume a mandatory token; raise `UnexpectedEnd`/`UnexpectedToken` on mismatch |
| `_parse_statement()` | New | Dispatch on `IDENT '='` vs. expression; return `Statement` |
| `_parse_arglist()` | Unchanged | Parse zero-or-more comma-separated expressions |

---

## 7. Error Handling

The parser raises errors only from `_parse_primary`, `_expect`, `_parse_statement` (implicitly via `_parse_expr`), and `parse_program`. No new error types are introduced.

| Condition | Error | Example |
|---|---|---|
| Token after complete program | `UnexpectedToken` | `2 + 3 4` (no semicolon between) |
| EOF where statement expected | `UnexpectedEnd` | `x = ` (rhs missing) |
| EOF where operand expected | `UnexpectedEnd` | `2 +` |
| Wrong token where operand expected | `UnexpectedToken` | `2 + )` |
| EOF where `)` expected | `UnexpectedEnd` | `(2 + 3` or `sqrt(9` |
| Wrong token where `)` expected | `UnexpectedToken` | `(2 + 3 4` |
| `IDENT '='` with no following expression | `UnexpectedEnd` or `UnexpectedToken` | `x =` or `x = )` |
| Bare IDENT (no `=`) | emits `Name` node — not a parse-time error |  |

The parser never raises `UndefinedVariable`, `ConstantReassignment`, `UnknownFunction`, `WrongArity`, or `DomainError`; those are evaluator concerns.

**Dependency error propagation:** Errors from `_parse_expr` and below bubble up through `_parse_statement` and `parse_program` without being caught or re-wrapped.

---

## 8. Testing Strategy

Tests live in `tests/test_parser.py`. All existing v0.2.0 tests remain valid and green — no existing production rules change and `parse()` is replaced with `parse_program()` (tests that called `.parse()` are updated mechanically to call `.parse_program()` and access `.body[0]` for single-statement inputs).

### 8.1 Regression: existing tests

Update call-sites: `Parser(Lexer(expr)).parse()` → `Parser(Lexer(expr)).parse_program().body[0]` for all single-expression tests. No assertion logic changes.

### 8.2 New happy-path tests: `parse_program`

| Input | Expected `Program.body` |
|---|---|
| `"x = 5"` | `[Assignment("x", Number(5.0))]` |
| `"x = 5; y = x * 2"` | `[Assignment("x", Number(5.0)), Assignment("y", BinaryOp("*", Name("x"), Number(2.0)))]` |
| `"x = 5; x + 1"` | `[Assignment("x", Number(5.0)), BinaryOp("+", Name("x"), Number(1.0))]` |
| `"2 + 3"` | `[BinaryOp("+", Number(2.0), Number(3.0))]` |
| `"x = 5;"` (trailing semicolon) | `[Assignment("x", Number(5.0))]` |
| `"x = 5; y = 3;"` (trailing semicolon) | `[Assignment("x", Number(5.0)), Assignment("y", Number(3.0))]` |
| `"pi"` (single name, program form) | `[Name("pi")]` |
| `"x = sqrt(9)"` | `[Assignment("x", Call("sqrt", [Number(9.0)]))]` |
| `"x = -5"` | `[Assignment("x", UnaryOp("-", Number(5.0)))]` |

### 8.3 `_peek_next` and lookahead correctness

```python
def test_assignment_then_expression():
    prog = Parser(Lexer("x = 5; x + 1")).parse_program()
    assert prog.body[0] == Assignment("x", Number(5.0))
    assert prog.body[1] == BinaryOp("+", Name("x"), Number(1.0))

def test_ident_without_equals_is_name_not_assignment():
    prog = Parser(Lexer("x + 1")).parse_program()
    assert prog.body[0] == BinaryOp("+", Name("x"), Number(1.0))
```

These two cases exercise both branches of `_parse_statement` for an `IDENT`-starting input and verify that `_peek_next` does not mis-classify.

### 8.4 Trailing semicolon tests

```python
def test_trailing_semicolon_accepted():
    prog = Parser(Lexer("x = 5;")).parse_program()
    assert len(prog.body) == 1
    assert prog.body[0] == Assignment("x", Number(5.0))

def test_trailing_semicolon_multi_stmt():
    prog = Parser(Lexer("x = 5; y = 3;")).parse_program()
    assert len(prog.body) == 2
```

### 8.5 Error-path tests

```python
@pytest.mark.parametrize("source,error_type", [
    ("x =",    UnexpectedEnd),    # assignment with missing rhs
    ("x = )",  UnexpectedToken),  # assignment with invalid rhs
    ("x = 5 y = 3", UnexpectedToken),  # missing semicolon separator
])
def test_parse_program_errors(source, error_type):
    with pytest.raises(error_type):
        Parser(Lexer(source)).parse_program()
```

### 8.6 What to mock

Nothing. The parser is deterministic and depends only on `Lexer`, which has no I/O. Tests construct a `Lexer` from a string literal and pass it to `Parser` directly.

### 8.7 Coverage targets

- Both branches of `_parse_statement` (`IDENT '='` and expression fall-through).
- `_peek_next` called and not called (to verify the lazy slot works in both states).
- `parse_program` loop: zero iterations (single statement), one or more iterations, trailing-semicolon break.
- All existing v0.2.0 branch targets in `_parse_primary` and `_parse_arglist`.

---

## 9. Dependencies

| Dependency | Direction | What is used |
|---|---|---|
| `src/calc/lexer.py` | import | `Lexer`, `Token`, `TokenType` (including new `SEMICOLON`, `EQUALS`) |
| `src/calc/errors.py` | import | `UnexpectedToken`, `UnexpectedEnd` |
| `src/calc/evaluator.py` | consumed by (one-way) | evaluator imports `ASTNode`, `Assignment`, `Program`, `Statement` from `parser.py` |

`TokenType.SEMICOLON` and `TokenType.EQUALS` must be added to `lexer.py` before `parser.py` is extended (HLD key design decision, research #112).

The parser module has no circular imports. `errors.py` has no dependencies; `lexer.py` has no dependencies; `parser.py` depends on both.
