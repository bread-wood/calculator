# High-Level Design — Calculator v0.3.0 (Variables)

**Milestone:** v0.3.0
**Date:** 2026-03-05
**Status:** Draft

---

## System Overview

The calculator is a single-binary command-line tool (`calc`) that accepts one arithmetic
expression — or a semicolon-separated sequence of statements — as a shell argument,
evaluates them in order, and prints the result of the last statement to stdout. It targets
developers who want quick calculations without leaving the terminal. The implementation is
in Python and ships with no external runtime dependencies beyond the Python standard library.

The pipeline has four stages: the **Lexer** tokenises the raw input string; the **Parser**
consumes the token stream and builds an explicit AST rooted at a `Program` node; the
**Evaluator** executes each statement in order, maintaining a mutable variable environment;
and the **Formatter** converts the final `float` result to a clean string for stdout. All
errors are represented as `CalcError` subclass instances and are caught at the CLI boundary,
which is the sole owner of stderr writes and process exit codes.

The codebase has five modules: `cli` (`__main__.py`), `lexer`, `parser`, `evaluator`, and
`errors`. They form a strict dependency chain: cli → evaluator → parser → lexer; `errors`
has no dependencies.

The evaluator supports 12 built-in mathematical functions (`sqrt`, `abs`, `floor`, `ceil`,
`round`, `sin`, `cos`, `tan`, `log`, `exp`, `pow`, `atan2`) and 2 named constants (`pi`,
`e`). In v0.3.0 the language is extended with named variable assignment and multi-statement
programs: a user may write `x = 5; y = x * 2; y + 1` as a single quoted argument.
Variables are scoped to the single invocation — no state persists between runs.

The design lays a forward-compatible foundation for v0.4.0 function parameters: the scope
model introduced here (a fresh dict per invocation, never mutating `_DEFAULT_ENV`) must be
extensible to a scope chain without a breaking rewrite (spec constraint; confirmed viable
by research issue #109).

**Key constraints:**
- Single-argument invocation: `calc '<expression-or-program>'`
- Runs on macOS and Linux with no external runtime dependencies beyond stdlib
- `make test` must pass clean on both platforms
- Completes any valid expression in under 100 ms
- Flat variable namespace; no block scoping in this version
- Named constants `pi` and `e` are read-only; reassignment raises an error
- Variables are evaluated eagerly and in order
- All v0.1.x and v0.2.x behaviour is preserved unchanged

**Non-goals:**
- Persistence across invocations.
- Block scoping or nested scopes.
- User-defined functions (v0.4.0).
- Interactive REPL mode.
- Windows support.

---

## Architecture

### Top-level component diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  CLI Entry Point  (__main__.py)                                   │
│                                                                   │
│  1. Parse argv                                                    │
│  2. Lex + parse → Program node                                    │
│  3. For each Statement in Program.body:                           │
│        result = execute_statement(stmt, env)                      │
│  4. Print result of last statement                                │
└─────────────┬──────────────────────────────────┬─────────────────┘
              │ Lexer(source)                      │ execute_statement(stmt, env)
              ▼                                    ▼
┌─────────────────────┐              ┌───────────────────────────────┐
│  Lexer  (lexer.py)  │              │  Evaluator  (evaluator.py)    │
│                     │              │                               │
│  TokenType +        │              │  evaluate(ASTNode, env)       │
│  SEMICOLON, EQUALS  │              │   → float                     │
│  Token stream       │              │                               │
└─────────────────────┘              │  execute_statement(stmt, env) │
              │                      │   → float | None              │
              ▼                      │                               │
┌─────────────────────┐              │  _CONSTANTS: frozenset        │
│  Parser  (parser.py)│              │  _DEFAULT_ENV: MappingProxy   │
│                     │              └───────────────────────────────┘
│  parse_program()    │
│   → Program         │              ┌───────────────────────────────┐
│  Program.body:      │              │  Errors  (errors.py)          │
│   list[Statement]   │              │                               │
│  Statement =        │              │  UndefinedVariable (renamed)  │
│   Assignment|ASTNode│              │  ConstantReassignment (new)   │
└─────────────────────┘              └───────────────────────────────┘
```

### Data flow

```
argv[1]
  │
  ▼
Lexer.next_token()  ──►  Token stream (SEMICOLON, EQUALS now included)
  │
  ▼
Parser.parse_program()  ──►  Program(body=[stmt, stmt, ...])
  │
  ▼  (iterate Program.body)
execute_statement(stmt, env)
  │
  ├─ Assignment:  evaluate(stmt.value, env)  →  float
  │               check _CONSTANTS           →  ConstantReassignment?
  │               env[stmt.name] = float     →  env mutated
  │               return float
  │
  └─ ASTNode:     evaluate(stmt, env)        →  float
                  return float
  │
  ▼
result of last statement  ──►  print to stdout
```

### Key design decisions

| Decision | Choice | Research basis |
|---|---|---|
| Python implementation | CI already uses `uv run pytest`; stdlib covers all requirements | `testing-strategy.md`, `07-project-layout-makefile-conventions.md` |
| Recursive descent parser | Zero deps; each grammar rule is one function; additive extension path for functions and variables | `parser-architecture.md` |
| Explicit AST (not direct eval) | Clean separation of parse from evaluate; evaluator is independently testable; AST is required for variable binding | `parser-architecture.md` |
| `float64` as sole numeric type | Single type handles all spec cases; `isinf` detects overflow; `isclose`-to-integer check strips `.0` | `numeric-representation.md` |
| `CalcError` exception hierarchy | One error class per variant; error messages defined in one place; layers raise errors, never write to stderr | `04-error-taxonomy-and-exit-codes.md` |
| Lazy/pull lexer | No intermediate token list allocation; parser calls `next_token()` on demand | `lexer-design.md` |
| `src/` layout with `uv` | Modern PyPA convention; `uv sync --frozen` gives reproducible envs on both platforms | `07-project-layout-makefile-conventions.md` |
| Single `IDENT` token type for all named identifiers | Lexer stays context-free; constants, functions, and variables share one token type | #38, #43, #53, #73 |
| `COMMA` as first-class `TokenType` | Consistent with every other syntactically meaningful single-char token; avoids coupling parser to lexer's `UNKNOWN` fallthrough | #65 |
| `Name` AST node (eval-time lookup) vs parse-time constant folding | Parser stays table-agnostic; same node type serves user variables without parser change | #43, #56 |
| Separate `_DEFAULT_ENV` (constants) and `_FUNCTION_TABLE` (functions) | Grammar disambiguates (`IDENT LPAREN` → `Call`; bare `IDENT` → `Name`); separate tables prevent variable shadowing of functions | #39, #43, #56 |
| `FunctionEntry` dataclass with `domain_check` predicate | Domain constraints co-located with function entry; explicit, independently testable; avoids catching `ValueError` from `math.*` | #39, #40, #54 |
| `float()` wrappers for `floor`/`ceil` in function table | Keeps `FunctionEntry.fn: Callable[..., float]` homogeneous; aligns with `_round_half_away` pattern | #67 |
| `_round_half_away` helper (not built-in `round`) | Python 3 `round()` uses banker's rounding; spec requires round-half-away-from-zero (`round(2.5)` → `3`) | #41, #75 |
| `str(value)` in `format_result` decimal branch | Gives the shortest round-trip string; matches all spec-mandated decimal outputs | #44, #57 |
| `description()` method on `CalcError` (replaces `_MESSAGES` dict) | Parameterized errors (`UnknownFunction`, `WrongArity`) cannot be expressed with a static dict; method dispatch is uniform | #55, #68 |
| Look-ahead guard in `_scan_number` for `e/E` | Bare `e` is a valid constant; `2e` must not produce a malformed `NUMBER("2e")` token | #66 |
| Arity validation in evaluator (not parser) | Parser stays table-agnostic; standard pattern for interpreted languages | #54 |
| Lookahead strategy | 2-token window (`_lookahead` slot, lazy) | #110 Option A |
| Statement dispatch | New `_parse_statement()` method | #110 Q2 |
| Trailing semicolons | Accepted | #110 Q3 |
| `parse()` rename | `parse_program() → Program` | #110 Q4, #113 Q2 |
| AST: assignment node | `Assignment(name, value)` dataclass | #113 Q1 |
| AST: program wrapper | `Program(body: list[Statement])` | #113 Q2 |
| `ASTNode` union | Unchanged (expression-level only) | #113 Q3 |
| Statement union | `Statement = Assignment \| ASTNode` | #113 Q3 |
| Evaluator split | `evaluate()` pure; `execute_statement()` new | #113 Q4 |
| `_DEFAULT_ENV` safety | `MappingProxyType`; fresh copy per call | #114 Q4 |
| Constant protection | `_CONSTANTS: frozenset` in `evaluator.py` | #114 Q3, #111 Q4 |
| `UnknownName` rename | `UndefinedVariable` | #111 Q2 |
| New error | `ConstantReassignment` | #111 Q3 |
| Token additions | `SEMICOLON`, `EQUALS` in `_SINGLE_CHAR` | #112 |
| Scope forward-compat | Fresh user-frame per invocation; never mutate `_DEFAULT_ENV` | #109, #114 |

---

## Module Breakdown

### Module: lexer

**Responsibility:** Convert a raw source string into a flat token stream with no
semantic interpretation.

**Key interfaces:**
- `TokenType` enum — `NUMBER`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `LPAREN`, `RPAREN`,
  `EOF`, `UNKNOWN`, `IDENT`, `COMMA`, `SEMICOLON`, `EQUALS` (13 types total)
- `Token(type: TokenType, value: str)` dataclass
- `Lexer(source: str)` class with `next_token() → Token`

**Files:** `src/calc/lexer.py`

**Dependencies:** none (stdlib only)

---

### Module: parser

**Responsibility:** Consume a token stream from `Lexer` and produce a typed AST rooted
at a `Program` node.

**Key interfaces:**
- `ASTNode` union type alias: `Number | BinaryOp | UnaryOp | Name | Call`
- `Number(value: float)` — numeric literal
- `BinaryOp(op: str, left: ASTNode, right: ASTNode)` — binary arithmetic or comparison
- `UnaryOp(op: str, operand: ASTNode)` — unary minus
- `Name(name: str)` — bare identifier (variable or constant lookup)
- `Call(func: str, args: list[ASTNode])` — function call
- `Assignment(name: str, value: ASTNode)` — variable assignment statement
- `Program(body: list[Statement])` — sequence of statements (top-level root)
- `Statement = Assignment | ASTNode` type alias
- `Parser(lexer: Lexer)` class with `parse_program() → Program`

**Files:** `src/calc/parser.py`

**Dependencies:** `lexer` (TokenType, Lexer, Token)

---

### Module: evaluator

**Responsibility:** Walk the AST recursively and produce a `float` result; maintain a
mutable variable environment across statement execution; resolve named constants and
dispatch built-in function calls; enforce arity, domain, and constant-reassignment
constraints; detect overflow.

**Key interfaces:**
- `evaluate(node: ASTNode, env: dict[str, float] | None = None) → float`
- `execute_statement(stmt: Statement, env: dict[str, float]) → float | None`
- `format_result(value: float) → str` — `"5"` for whole results, `str(value)` for decimals
- `_DEFAULT_ENV: MappingProxyType[str, float]` — built-in constants (`pi`, `e`); never mutated
- `_CONSTANTS: frozenset[str]` — names that may not be reassigned (`{"pi", "e"}`)
- `_FUNCTION_TABLE: dict[str, FunctionEntry]` — 12 built-in functions
- `FunctionEntry(name, arity, fn, domain_check)` — frozen dataclass

**Files:** `src/calc/evaluator.py`

**Dependencies:** `parser` (ASTNode, Assignment), `errors` (all CalcError subclasses), `math` (stdlib)

---

### Module: errors

**Responsibility:** Define the public `CalcError` hierarchy; provide human-readable
error descriptions via `description()` methods on each subclass.

**Key interfaces:**
- `CalcError(Exception)` — base class with abstract `description() → str`
- `ExpectedSingleArg` — wrong number of CLI arguments
- `EmptyExpression` — empty string argument
- `UnexpectedToken(token)` — token where a different one was expected
- `UnexpectedEnd` — expression ends mid-parse
- `DivisionByZero` — division or modulo by zero
- `Overflow` — result exceeds float range
- `UnknownFunction(name)` — call to unregistered function name
- `WrongArity(name, expected)` — wrong number of arguments to a function
- `DomainError()` — argument outside function's mathematical domain
- `UndefinedVariable(name: str)` — `Name` node not found in the variable environment
- `ConstantReassignment(name: str)` — attempt to assign to a read-only constant
- `error_message(e: CalcError) → str` — returns `"error: <e.description()>"`

**Files:** `src/calc/errors.py`

**Dependencies:** none

---

### Module: cli

**Responsibility:** Parse CLI arguments, drive the lex → parse → execute pipeline, format output to stdout/stderr, and set the exit code.

**Key interfaces:**
- `main()` entry point called from `__main__.py`
- Iterates `Program.body`, calling `execute_statement(stmt, env)` per statement
- Prints result of last statement (integer if whole, decimal otherwise)

**Files:** `src/calc/__main__.py`

**Dependencies:** `lexer`, `parser`, `evaluator`, `errors`

---

## Cross-Cutting Concerns

### Error handling strategy

All errors descend from `CalcError`. The CLI catches `CalcError`, writes
`"error: " + e.description()` to stderr, and exits 1. No error type is
swallowed silently. The two new error conditions in v0.3.0:

- `UndefinedVariable` — raised by `evaluate()` when a `Name` node is not
  found in `env`.
- `ConstantReassignment` — raised by `execute_statement()` before any write
  to `env` when the target name is in `_CONSTANTS`.

All v0.2.x arithmetic errors (`DivisionByZero`, `DomainError`, `Overflow`)
and parse errors propagate unchanged.

### Testing approach

- Unit tests per module (`test_lexer.py`, `test_parser.py`, `test_evaluator.py`,
  `test_errors.py`) — test new tokens, new AST nodes, `execute_statement`,
  `UndefinedVariable`, and `ConstantReassignment` in isolation.
- CLI integration tests (`test_cli.py`) — cover every success criterion from
  the spec: multi-statement evaluation, variable reference, constant protection,
  trailing semicolons, last-statement-is-assignment, all inherited error paths.
- Regression: the full existing test suite must pass without modification
  (except the one `test_unknown_name_message` assertion updated for the rename,
  and import references to `UnknownName` → `UndefinedVariable`).

### Configuration and environment

- No configuration files; all behaviour is determined by CLI arguments.
- `_DEFAULT_ENV` is a `MappingProxyType` module-level constant in
  `evaluator.py`; it is the single source of truth for built-in constants.
- Fresh `dict(_DEFAULT_ENV)` is created per evaluation invocation — no
  mutable global state.

### Observability / logging

No logging in v0.3.0. All user-visible output is either the numeric result
on stdout or a `"error: ..."` line on stderr, matching the v0.2.x contract.

---

## Open Questions

The following decisions are deferred to the LLD for each module:

1. **`parser` LLD** — Exact dataclass field ordering and whether `Assignment`
   and `Program` live alongside existing nodes in `parser.py` or move to a
   separate `ast.py`.
2. **`evaluator` LLD** — Whether `execute_statement` is a standalone function
   or a method; exact handling when the last statement is an `Assignment`
   (return assigned value vs. `None`).
3. **`cli` LLD** — How the `env` dict is threaded across the statement loop
   and whether `__main__.py` constructs it or delegates to the evaluator.
4. **`errors` LLD** — Whether `UndefinedVariable` preserves the existing
   `description()` wording change (`"undefined variable: x"` without quotes)
   and the exact `ConstantReassignment.description()` output (`"cannot reassign
   constant: pi"` without quotes, per spec).
