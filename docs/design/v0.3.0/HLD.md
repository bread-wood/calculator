# High-Level Design — Calculator v0.3.0 (Variables)

**Milestone:** v0.3.0
**Date:** 2026-03-05
**Status:** Draft

---

## System Overview

v0.3.0 extends the calculator CLI with named variable assignment and
multi-statement programs. A user may write `x = 5; y = x * 2; y + 1` as a
single quoted argument; the calculator evaluates each statement in order and
prints the value of the last statement. Variables are scoped to the single
invocation — no state persists between runs.

The design must also lay a forward-compatible foundation for v0.4.0 function
parameters: the scope model introduced here must be extensible to a scope
chain without requiring a breaking rewrite (spec constraint; confirmed viable
by research issue #109).

**Key constraints (from spec):**
- Flat variable namespace; no block scoping in this version.
- Named constants `pi` and `e` are read-only; reassignment raises an error.
- Variables are evaluated eagerly and in order.
- All v0.1.x and v0.2.x behaviour is preserved unchanged.

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

**Responsibility:** Convert a raw source string into a flat token stream, including the two new tokens required by v0.3.0 grammar.

**Key interfaces:**
- `TokenType` enum — extended with `SEMICOLON` and `EQUALS`
- `Token(type, value)` dataclass
- `Lexer(source: str)` class with `next_token() → Token`

**Files:** `src/calc/lexer.py`

**Dependencies:** none (stdlib only)

---

### Module: parser

**Responsibility:** Consume a token stream from `Lexer` and produce a typed AST rooted at a `Program` node.

**Key interfaces:**
- `Assignment(name: str, value: ASTNode)` dataclass
- `Program(body: list[Statement])` dataclass
- `Statement = Assignment | ASTNode` type alias
- `Parser(lexer: Lexer)` class with `parse_program() → Program`

**Files:** `src/calc/parser.py`

**Dependencies:** `lexer` (TokenType, Lexer, Token)

---

### Module: evaluator

**Responsibility:** Walk an AST and produce a numeric result, maintaining a mutable variable environment; enforce constant protection.

**Key interfaces:**
- `evaluate(node: ASTNode, env: dict[str, float] | None) → float`
- `execute_statement(stmt: Statement, env: dict[str, float]) → float | None`
- `_CONSTANTS: frozenset[str]`
- `_DEFAULT_ENV: MappingProxyType`

**Files:** `src/calc/evaluator.py`

**Dependencies:** `parser` (ASTNode, Assignment), `errors` (UndefinedVariable, ConstantReassignment, and inherited errors)

---

### Module: errors

**Responsibility:** Define the public error hierarchy; provide human-readable error descriptions.

**Key interfaces:**
- `CalcError` base class with `description() → str`
- `UndefinedVariable(name: str)` — renamed from `UnknownName`
- `ConstantReassignment(name: str)` — new in v0.3.0
- All existing v0.2.x error classes unchanged

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
