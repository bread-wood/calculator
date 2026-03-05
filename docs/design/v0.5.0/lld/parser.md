# Low-Level Design — `parser` Module (v0.5.0)

**Milestone:** v0.5.0
**Module:** `parser` (`src/calc/parser.py`)
**Date:** 2026-03-05
**Status:** Draft

---

## 1. Scope

The `parser` module consumes a token stream produced by `Lexer` and builds a typed
Abstract Syntax Tree (AST) rooted at a `Program` node. It is used by both the legacy
expression pipeline (`_legacy_eval`) and the plot path (`run_plot`). No changes are
made to this module in v0.5.0; this LLD documents the existing implementation as it
stands going into v0.5.0 to provide a stable reference baseline.

---

## 2. Data Structures

### 2.1 AST Node Types

All node types are plain `@dataclass` instances. Equality is structural (default
`__eq__` from `dataclass`). No `frozen=True` is required at this layer; the AST is
immutable by convention once `parse_program()` returns.

```python
@dataclass
class Number:
    value: float          # result of float() on the raw NUMBER lexeme

@dataclass
class BinaryOp:
    op: str               # one of "+", "-", "*", "/"
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str               # always "-" in v0.5.0
    operand: ASTNode

@dataclass
class Name:
    name: str             # bare identifier: variable or constant reference

@dataclass
class Call:
    func: str             # function name
    args: list[ASTNode]   # may be empty (zero-arg call)

ASTNode = Number | BinaryOp | UnaryOp | Name | Call
```

### 2.2 Statement Types

```python
@dataclass
class Assignment:
    name: str             # variable name (left-hand side)
    value: ASTNode        # right-hand expression

@dataclass
class FunctionDef:
    name: str             # function name
    params: list[str]     # ordered formal parameter names; may be empty
    body: ASTNode         # expression tree

@dataclass
class Program:
    body: list[Statement] # ordered statement list; empty only for empty input

Statement = Assignment | FunctionDef | ASTNode
```

### 2.3 Parser Internal State

```python
class Parser:
    _lexer: Lexer         # token source (pull/lazy)
    _current: Token       # token at the parse head (always populated)
    _lookahead: Token | None  # one-token read-ahead buffer; None when empty
```

The one-token lookahead (`_lookahead`) is populated only when `_peek_next()` is
called and cleared on the next `_advance()`. This keeps the lexer pull-based with
at most one extra token buffered — sufficient to distinguish `IDENT EQUALS` (assignment
head) from `IDENT LPAREN` (call) and `IDENT <other>` (bare name).

---

## 3. Grammar

The grammar recognised by the parser, in EBNF, is:

```
program     = { statement [ ";" ] } EOF
statement   = funcdef
            | IDENT "=" expression          (* assignment — only when IDENT followed by "=" *)
            | expression

funcdef     = "def" IDENT "(" param_list ")" "=" expression
param_list  = [ IDENT { "," IDENT } ]

expression  = term { ( "+" | "-" ) term }   (* left-associative *)
term        = factor { ( "*" | "/" ) factor } (* left-associative *)
factor      = unary
unary       = "-" unary | primary            (* right-recursive; right-associative *)
primary     = NUMBER
            | "(" expression ")"
            | IDENT "(" arg_list ")"         (* function call *)
            | IDENT                          (* variable / constant reference *)

arg_list    = [ expression { "," expression } ]
```

**Precedence (highest to lowest):**

| Level | Operators | Associativity |
|-------|-----------|---------------|
| 4 | unary `-` | right |
| 3 | `*`, `/` | left |
| 2 | `+`, `-` | left |
| 1 | `;` (separator) | — |

---

## 4. Key Algorithms

### 4.1 Recursive Descent

Each grammar rule maps to exactly one private method. The parse head (`_current`) is
always a valid unconsumed token; advancing past it is done via `_advance()`.

```
parse_program()
  └── _parse_statement()
        ├── _parse_funcdef()             (when _current == DEF)
        │     └── _parse_param_list()
        │           └── _parse_expr()   (body)
        ├── Assignment branch            (when _current == IDENT and _peek_next == EQUALS)
        │     └── _parse_expr()
        └── _parse_expr()               (all other cases)
              └── _parse_term()
                    └── _parse_factor()
                          └── _parse_unary()
                                └── _parse_primary()
                                      └── _parse_arglist()
```

### 4.2 One-Token Lookahead for Assignment Detection

The parser uses a one-token lookahead exclusively to decide between an assignment
statement and a bare expression starting with an identifier:

```python
def _parse_statement(self) -> Statement:
    if self._current.type == TokenType.DEF:
        return self._parse_funcdef()
    if (self._current.type == TokenType.IDENT
            and self._peek_next().type == TokenType.EQUALS):
        name = self._advance().value   # consume IDENT
        self._advance()                # consume EQUALS
        ...
        return Assignment(name=name, value=self._parse_expr())
    return self._parse_expr()
```

`_peek_next()` reads one token from the lexer into `_lookahead` (if not already
populated) and returns it without consuming it. The next call to `_advance()` drains
`_lookahead` before requesting a new token from the lexer. This guarantees the lexer
is never called more than one position ahead of the parse head.

### 4.3 Left-Associativity via Iteration

Binary operators at each precedence level are handled with a `while` loop rather than
recursion, which produces naturally left-associative trees without growing the call
stack:

```python
def _parse_expr(self) -> ASTNode:
    node = self._parse_term()
    while self._current.type in (TokenType.PLUS, TokenType.MINUS):
        op = self._advance().value
        right = self._parse_term()
        node = BinaryOp(op=op, left=node, right=right)
    return node
```

The same pattern is used for `_parse_term()`. The result is a left-leaning tree:
`2 - 3 - 4` → `BinaryOp("-", BinaryOp("-", 2, 3), 4)`.

### 4.4 Right-Associativity of Unary Negation via Recursion

`_parse_unary()` calls itself recursively when a `-` prefix is found, which produces
right-associative chaining: `--5` → `UnaryOp("-", UnaryOp("-", 5))`.

### 4.5 Semicolon Handling in `parse_program()`

Semicolons are optional statement separators and also optional trailing characters.
After parsing each statement:

- If the next token is `SEMICOLON`, it is consumed unconditionally.
- If the next token is `EOF`, the loop exits cleanly.
- Any other token raises `UnexpectedToken`.

This allows `"x = 5"`, `"x = 5;"`, `"x = 5; x + 1"`, and `"x = 5; x + 1;"` but
rejects `"x = 5 x + 1"` (two statements without a separator).

---

## 5. Public API

```python
# src/calc/parser.py

# -- AST node types (all @dataclass) --
class Number:      value: float
class BinaryOp:    op: str; left: ASTNode; right: ASTNode
class UnaryOp:     op: str; operand: ASTNode
class Name:        name: str
class Call:        func: str; args: list[ASTNode]

ASTNode = Number | BinaryOp | UnaryOp | Name | Call

# -- Statement types (all @dataclass) --
class Assignment:  name: str; value: ASTNode
class FunctionDef: name: str; params: list[str]; body: ASTNode
class Program:     body: list[Statement]

Statement = Assignment | FunctionDef | ASTNode

# -- Parser class --
class Parser:
    def __init__(self, lexer: Lexer) -> None: ...
    def parse_program(self) -> Program: ...
```

**Usage pattern (both pipelines):**

```python
from calc.lexer import Lexer
from calc.parser import Parser

ast = Parser(Lexer(source)).parse_program()
```

For the plot path, only single-expression programs are expected:
`ast.body[0]` is the expression `ASTNode` passed to `evaluate()` and `build_scene()`.

---

## 6. Error Handling

The parser raises exactly two error classes, both from `calc.errors`:

| Error class | `description()` | When raised |
|---|---|---|
| `UnexpectedToken` | `"unexpected token"` | Valid token in a syntactically illegal position; also raised on unrecognised characters produced by the lexer as `UNKNOWN` tokens bubbling up to `_parse_primary()` |
| `UnexpectedEnd` | `"unexpected end of expression"` | `EOF` is reached where an operand or closing delimiter was expected |

**Decision table for `_expect(type)`:**

```
_current.type == type        → consume and return token (success)
_current.type == EOF         → raise UnexpectedEnd
_current.type == other       → raise UnexpectedToken
```

**Distinction rule:** `UnexpectedEnd` is used whenever the error is triggered by
`EOF`; `UnexpectedToken` is used for all other wrong-token situations. This
distinction is tested explicitly (see §7).

**The parser does not validate semantics.** The following are intentionally not
checked at parse time:

- Whether a `Name` refers to an in-scope variable or constant.
- Whether a `Call` refers to a defined function.
- Whether argument count matches function arity.
- Whether a `FunctionDef` redefines an existing function or builtin.
- Whether an `Assignment` targets a constant.

All semantic checks are deferred to `evaluator.py`.

---

## 7. Test Strategy

### 7.1 No New Tests Required for v0.5.0

`tests/test_parser.py` is unchanged in v0.5.0. The parser itself is unchanged. The
existing test suite (documented below) constitutes the full test obligation for this
module.

### 7.2 Existing Test Coverage

The existing `tests/test_parser.py` covers the following areas, all of which must
continue to pass:

**Literals and arithmetic:**
- `Number` parsing from integer and float lexemes
- `BinaryOp` for all four operators
- Precedence: `*`/`/` over `+`/`-`
- Left-associativity: `2 - 3 - 4`
- Parenthesised grouping

**Unary negation:**
- Single negation: `-5`
- Chained negation: `--5`
- Mixed: `2 - -3`

**Names and calls:**
- Bare `Name` node for identifiers (`pi`, `e`, `x`)
- Zero-arg `Call`: `f()`
- Single-arg `Call`: `sqrt(9)`
- Multi-arg `Call`: `pow(2, 10)`
- Call with expression argument: `sqrt(2 + 3)`
- Nested calls: `pow(sqrt(4), 2)`
- Name in binary expression: `2 * pi`

**Error cases (expressions):**
- `"2 +"` → `UnexpectedEnd`
- `"(2 + 3"` → `UnexpectedEnd`
- `"2 3"` → `UnexpectedToken`
- `"2 + )"` → `UnexpectedToken`
- `"(2 + 3 4"` → `UnexpectedToken`
- `"sqrt("` → `UnexpectedEnd`
- `"sqrt(9"` → `UnexpectedEnd`
- `"sqrt(9 4"` → `UnexpectedToken`
- `"f(1,)"` → `UnexpectedEnd` or `UnexpectedToken`

**Assignment (v0.3.0):**
- `"x = 5"` → `Program([Assignment("x", Number(5.0))])`
- `"x = 5; x + 1"` → two-statement program
- IDENT without `=` parsed as `Name`, not `Assignment`
- Trailing semicolon accepted (single and multi-statement)
- Three-statement programs
- Error cases: `"x ="`, `"x = )"`, `"x = 5 y = 3"`
- Assignment with call RHS: `"x = sqrt(9)"`
- Assignment with unary RHS: `"x = -5"`

**Function definitions (v0.4.0):**
- Zero-param `def`: `def f() = 1`
- One-param `def`: `def f(x) = x`
- Multi-param `def`: `def f(x, y) = x + y`
- Body with compound expression: `def g(x) = x * 2 + 1`
- `def` followed by call in same program
- Call in expression: `f(1) + 2`
- Body using another call: `def h(x) = sqrt(x)`
- Error cases: missing name, missing `(`, non-ident param, missing `)`, missing `=`, empty body

### 7.3 Test Helpers

```python
def parse(expr: str) -> Statement:
    """Parse a single-statement program and return body[0]."""
    return Parser(Lexer(expr)).parse_program().body[0]

def parse_program(expr: str) -> Program:
    """Parse a full program."""
    return Parser(Lexer(expr)).parse_program()
```

### 7.4 Property-Based Testing (Future Consideration)

Not required for v0.5.0. If added in a future milestone, the primary invariant to
verify would be:

> For any expression string `s` that parses without error, `parse(s)` returns an
> `ASTNode` such that its tree structure is consistent with the precedence/associativity
> rules of the grammar.

---

## 8. Module Dependencies

```
parser.py
  imports: calc.lexer  (Lexer, Token, TokenType)
           calc.errors (UnexpectedEnd, UnexpectedToken)
           dataclasses (dataclass)
  imported by: calc.evaluator
               calc.plotter  (via evaluator's evaluate())
               calc.__main__
               tests/test_parser.py
```

No changes to the dependency graph in v0.5.0.

---

## 9. Open Questions Resolved

The HLD listed no open questions for the `parser` module. The parser is unchanged in
v0.5.0 and no new design decisions are required.

The one relevant cross-module decision resolved here: the plot path passes
`ast.body[0]` (the `ASTNode` from a single-statement parse) directly to
`build_scene()` and `evaluate()`. The parser itself has no awareness of this usage;
it remains a general multi-statement parser.

---

## 10. Non-Goals for this Module

- **No syntax changes in v0.5.0.** The `x` free variable in `calc plot 'sin(x)'` is
  parsed as an ordinary `Name("x")` node, exactly as it would be in the legacy path.
  The parser does not need to know that `x` will be bound to a sampled float at
  evaluation time.
- **No exponentiation operator.** `**` or `^` are not in scope for v0.5.0.
- **No multi-variable expressions.** Treated at parse time as multiple `Name` nodes;
  the plot path constrains to a single free variable `x` at evaluation time, not at
  parse time.
