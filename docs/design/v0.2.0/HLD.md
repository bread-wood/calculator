# High-Level Design: Calculator v0.2.0

**Milestone:** v0.2.0
**Date:** 2026-03-04
**Status:** Draft

---

## System Overview

v0.2.0 extends the v0.1.x arithmetic calculator with named mathematical functions
(`sqrt`, `abs`, `floor`, `ceil`, `round`, `sin`, `cos`, `tan`, `log`, `exp`,
`pow`, `atan2`) and named constants (`pi`, `e`). The extension validates that the
v0.1.x parser architecture was designed with genuine extensibility: adding function-
call syntax and constant references requires only additive changes to all three
layers (lexer, parser, evaluator) with no restructuring of existing production rules,
AST nodes, or error-handling paths.

**Key constraints (inherited from v0.1.x):**
- macOS + Linux, Python stdlib only, no third-party runtime dependencies
- Single-line output, under 100 ms, no config files
- `make test` must pass clean on both platforms

**Non-goals for this version:**
- Inverse trig (`asin`, `acos`), `log2`, `log10`, degree mode
- User-defined variables (`x = 5`) — namespaces are designed to accommodate them
- User-defined functions, interactive REPL, Windows support

---

## Architecture

### Top-Level Component Diagram

```
 CLI argument
      │
      ▼
┌─────────────┐
│  __main__.py │  Entry point: validates CLI args, routes errors to stderr
└──────┬──────┘
       │ raw expression string
       ▼
┌─────────────┐
│   lexer.py  │  Tokenizes input → stream of Token objects
│             │  NEW: IDENT, COMMA token types; _scan_ident()
└──────┬──────┘
       │ Token stream
       ▼
┌─────────────┐
│   parser.py │  Recursive-descent parser → ASTNode tree
│             │  NEW: Name, Call AST nodes; _parse_primary() IDENT branch; _parse_arglist()
└──────┬──────┘
       │ ASTNode
       ▼
┌──────────────────────────────────┐
│          evaluator.py            │  Walks AST → float result
│                                  │  NEW: _DEFAULT_ENV (pi, e)
│  ┌──────────────┐                │       _FUNCTION_TABLE dispatch
│  │ functions.py │ ← (or inline)  │       DomainError, WrongArity, UnknownFunction checks
│  │ FUNCTION_TABLE│               │       float() wrappers for floor/ceil
│  └──────────────┘                │
└──────┬───────────────────────────┘
       │ float
       ▼
┌─────────────┐
│  format_result│  Integer vs. decimal formatting; str(value) for full precision
└──────┬──────┘
       │ string
       ▼
    stdout
```

### Data Flow

1. `__main__` receives the raw expression string from `sys.argv[1]`.
2. `Lexer` scans the string character-by-character, emitting a `Token` stream.
   - v0.2.0 adds `IDENT` tokens (alphabetic identifiers) and `COMMA` (`,`).
   - A look-ahead guard in `_scan_number` prevents `2e` from producing a
     malformed `NUMBER("2e")` token (research #66).
3. `Parser` consumes the token stream via recursive descent.
   - v0.2.0 adds an `IDENT` branch in `_parse_primary`: if the next token is
     `LPAREN`, emit `Call(name, args)`; otherwise emit `Name(name)`.
   - `_parse_arglist` handles zero-or-more comma-separated expressions.
4. `evaluate(node, env)` walks the AST recursively.
   - `Name` nodes look up `env` (the `_DEFAULT_ENV` dict seeded with `pi`/`e`).
   - `Call` nodes look up `_FUNCTION_TABLE` by name, validate arity, run the
     optional `domain_check` predicate, then call the function pointer.
   - All function entries return `float`; `floor`/`ceil` use `float()` wrappers.
5. `format_result(value)` converts the float to a string: integer output for
   whole-valued results, `str(value)` for decimals (full IEEE 754 precision).
6. All `CalcError` subclasses are caught at the `__main__` boundary, printed to
   stderr as `"error: <description>"`, and cause exit code 1.

### Key Design Decisions

| Decision | Rationale | Research |
|----------|-----------|----------|
| Single `IDENT` token type for all named identifiers | Lexer stays context-free; constants, functions, and future variables share one token type | #38, #43, #53, #73 |
| `COMMA` as first-class `TokenType` | Consistent with every other syntactically meaningful single-char token; avoids coupling parser to lexer's `UNKNOWN` fallthrough | #65 |
| `Name` AST node (eval-time lookup) vs parse-time constant folding | Parser stays table-agnostic; same node type serves future user variables without parser change | #43, #56 |
| Separate `_DEFAULT_ENV` (constants) and `_FUNCTION_TABLE` (functions) | Grammar already disambiguates (`IDENT LPAREN` → `Call`; bare `IDENT` → `Name`); separate tables prevent variable shadowing of functions | #39, #43, #56 |
| `FunctionEntry` dataclass with `domain_check` predicate | Domain constraints co-located with function entry; explicit, independently testable; avoids catching `ValueError` from `math.*` | #39, #40, #54 |
| `float()` wrappers for `floor`/`ceil` in function table | Keeps `FunctionEntry.fn: Callable[..., float]` homogeneous; aligns with `_round_half_away` pattern | #67 |
| `_round_half_away` helper (not built-in `round`) | Python 3 `round()` uses banker's rounding; spec requires round-half-away-from-zero (`round(2.5)` → `3`) | #41, #75 |
| `str(value)` in `format_result` decimal branch | Replaces `:.15g` which truncates to 15 significant digits; `str(float)` gives the shortest round-trip string, matching all spec-mandated decimal outputs | #44, #57 |
| `description()` method on `CalcError` (replaces `_MESSAGES` dict) | Parameterized errors (`UnknownFunction`, `WrongArity`) cannot be expressed with a static dict; method dispatch is uniform and extensible | #55, #68 |
| Look-ahead guard in `_scan_number` for `e/E` | Bare `e` is a valid constant in v0.2.0; `2e` must not produce a malformed `NUMBER("2e")` token that crashes with `ValueError` | #66 |
| Arity validation in evaluator (not parser) | Parser stays table-agnostic; standard pattern for interpreted languages; any `Call` node is valid AST | #54 |

---

## Module Breakdown

### Module: lexer

**Responsibility:** Scan an expression string into a flat sequence of typed `Token`
objects, with no semantic interpretation.

**Key interfaces:**
- `TokenType` enum — token categories; v0.2.0 adds `IDENT` and `COMMA`
- `Token(type: TokenType, value: str)` dataclass
- `Lexer(input: str)` — `next_token() -> Token`

**Files:** `src/calc/lexer.py`

**Dependencies:** none (stdlib only)

---

### Module: parser

**Responsibility:** Consume the token stream from `Lexer` and produce a typed AST
representing the expression's structure.

**Key interfaces:**
- `ASTNode` union type alias: `Number | BinaryOp | UnaryOp | Name | Call`
- `Number(value: float)`, `BinaryOp(op, left, right)`, `UnaryOp(op, operand)` — existing
- `Name(name: str)` — new v0.2.0; bare identifier (constant or future variable)
- `Call(func: str, args: list[ASTNode])` — new v0.2.0; function call expression
- `Parser(lexer: Lexer)` — `parse() -> ASTNode`

**Files:** `src/calc/parser.py`

**Dependencies:** `lexer` (for `TokenType`, `Token`, `Lexer`)

---

### Module: evaluator

**Responsibility:** Walk the AST recursively and produce a `float` result; resolve
named constants via `_DEFAULT_ENV`; dispatch function calls through `_FUNCTION_TABLE`;
enforce arity and domain constraints; detect overflow.

**Key interfaces:**
- `evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float`
  - `env` defaults to `_DEFAULT_ENV` (contains `pi`, `e`); callers may pass a
    custom dict for future variable support
- `format_result(value: float) -> str`
- `_DEFAULT_ENV: dict[str, float]` — module-level constant table
- `_FUNCTION_TABLE: dict[str, FunctionEntry]` — built from `FUNCTION_TABLE` list
- `FunctionEntry(name, arity, fn, domain_check)` — frozen dataclass

**Files:** `src/calc/evaluator.py`

**Dependencies:** `parser` (for AST node types), `errors` (for `CalcError` subclasses),
`math` (stdlib)

---

### Module: errors

**Responsibility:** Define the `CalcError` class hierarchy and the `error_message()`
formatter; each subclass carries its own `description()` method so parameterized
messages (`UnknownFunction`, `WrongArity`) are self-contained.

**Key interfaces:**
- `CalcError(Exception)` — base class with abstract `description() -> str`
- Existing subclasses: `ExpectedSingleArg`, `EmptyExpression`, `UnexpectedToken`,
  `UnexpectedEnd`, `DivisionByZero`, `Overflow`
- New v0.2.0 subclasses: `UnknownFunction(name)`, `WrongArity(name, expected)`,
  `DomainError()`
- `error_message(e: CalcError) -> str` — returns `"error: <e.description()>"`

**Files:** `src/calc/errors.py`

**Dependencies:** none

---

### Module: cli

**Responsibility:** Parse CLI arguments, invoke the pipeline (lexer → parser →
evaluator → format_result), write to stdout on success, catch all `CalcError`
exceptions and write to stderr with exit code 1.

**Key interfaces:**
- `main()` — called from `__main__.py`; no public API beyond the CLI contract

**Files:** `src/calc/__main__.py`

**Dependencies:** `lexer`, `parser`, `evaluator`, `errors`

---

## Cross-Cutting Concerns

### Error Handling Strategy

All errors that surface to the user are `CalcError` subclasses caught in
`__main__.main()`. The chain is:

```
lexer    →  UnexpectedToken (UNKNOWN token where expression token expected)
parser   →  UnexpectedToken, UnexpectedEnd
evaluator→  DivisionByZero, Overflow, DomainError, UnknownFunction, WrongArity
__main__ →  ExpectedSingleArg, EmptyExpression (CLI-level validation)
```

`CalcError` subclasses now carry a `description()` method instead of being looked
up in a static `_MESSAGES` dict. This allows `UnknownFunction` and `WrongArity` to
embed runtime data (function name, expected count) in their messages without
special-casing in `error_message()`. The `TypeError` guard for unregistered
subclasses is preserved (research #68).

Domain pre-validation (explicit `if x < 0` guards before `math.sqrt`) is used for
`sqrt` and `log` rather than catching `ValueError` from `math.*`, matching the
v0.1.x `DivisionByZero` pattern (research #40, #54).

`OverflowError` from `math.exp(large)` is caught at the function dispatch site and
re-raised as `Overflow()`, feeding into the existing overflow path.

### Testing Approach

Tests are distributed across all five existing test files following the v0.1.x
layered strategy (research #42, #58):

| File | Scope | New cases |
|------|-------|-----------|
| `test_lexer.py` | `IDENT`/`COMMA` tokens; `1e10` vs `2e` edge cases | ~9 |
| `test_parser.py` | `Name`, `Call` AST nodes; nested calls | ~8 |
| `test_evaluator.py` | 14 function/constant dispatch paths; 5 error-raise paths | ~21 |
| `test_errors.py` | `description()` messages for 3 new error classes | ~7 |
| `test_cli.py` | All 21 spec acceptance criteria (16 success + 5 error) | 21 |

No new test framework is needed; the existing pytest + subprocess harness fully
supports stderr/exit-code assertions (research #42).

CI matrix is extended with `macos-latest` to satisfy the
"passes clean on macOS and Linux" spec requirement (research #42).

### Configuration and Environment

No configuration files. All function and constant registrations are module-level
data structures (`FUNCTION_TABLE` list, `_DEFAULT_ENV` dict) in `evaluator.py`.
Adding a function requires one new `FunctionEntry` line; no parser or CLI changes.

### Observability / Logging

No logging. Output contract is identical to v0.1.x:
- Success: result string on stdout, newline, exit 0
- Error: `error: <description>` on stderr, newline, exit 1

---

## Open Questions

The following decisions are deferred to the LLD phase for each module:

1. **`functions.py` vs inline in `evaluator.py`:** Whether `FUNCTION_TABLE` and
   `FunctionEntry` live in a new `src/calc/functions.py` module or remain in
   `evaluator.py`. Research #39 and #54 suggest a dedicated module for
   discoverability; research #56 places `_DEFAULT_ENV` in `evaluator.py`. The LLD
   for `evaluator` should resolve this and ensure the import graph stays acyclic.

2. **`UnknownName` vs reusing `UnknownFunction` for bare-identifier lookup miss:**
   Research #56 proposes a separate `UnknownName` error for bare `Name` nodes that
   resolve to nothing in `env`. The LLD for `errors` should decide whether a distinct
   error class is needed or whether `UnknownFunction` is used for both cases (the
   spec only specifies the function-call error message).

3. **`_check_overflow` placement after `OverflowError` catch:** The LLD for
   `evaluator` should confirm whether `_check_overflow(result)` is still needed
   after the `OverflowError` catch for `exp`, or whether the catch alone is
   sufficient.

4. **CI workflow file path and matrix syntax:** The LLD for `ci` (if filed) or the
   implementation issue should confirm the exact `os` matrix addition to
   `.github/workflows/ci.yml`.
