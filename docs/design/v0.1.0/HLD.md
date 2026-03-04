# High-Level Design — Calculator CLI v0.1.0

**Milestone:** v0.1.0
**Date:** 2026-03-04
**Status:** Draft

---

## System Overview

The calculator is a single-binary command-line tool (`calc`) that accepts one arithmetic
expression as a shell argument, evaluates it, and prints the result to stdout. It targets
developers who want quick calculations without leaving the terminal. The implementation is
in Python (confirmed by CI toolchain: `uv run pytest`, `uv run ruff check`) and ships
with no external runtime dependencies beyond the Python standard library. It serves as the
Tier 1 proof-of-concept for validating the breadmin-composer pipeline end-to-end.

**Key constraints (from spec):**
- Single-argument invocation: `calc '<expression>'`
- Runs on macOS and Linux with no external runtime dependencies beyond stdlib
- `make test` must pass clean on both platforms
- Completes any valid expression in under 100 ms
- Parser architecture must extend to named functions and variables without a rewrite

**Non-goals (v0.1.0):**
- Variables and assignments (`x = 5`)
- Named functions (`sin`, `sqrt`, `pow`)
- Interactive REPL mode
- Windows support

---

## Architecture

### Top-Level Component Diagram

```
┌──────────────────────────────────────────────────────────┐
│  CLI Entry Point  (src/calc/__main__.py)                 │
│                                                          │
│  argv validation → error: expected a single quoted expr  │
│  empty-string check → error: empty expression            │
│  usage print → usage: calc '<expression>'                │
└────────────────────┬─────────────────────────────────────┘
                     │ raw expression string
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Lexer  (src/calc/lexer.py)                              │
│                                                          │
│  Scanner{input, cursor}                                  │
│  nextToken() → Token{type, value}                        │
│  Token types: NUMBER PLUS MINUS STAR SLASH               │
│               LPAREN RPAREN EOF UNKNOWN                  │
└────────────────────┬─────────────────────────────────────┘
                     │ token stream (pull/lazy)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Parser  (src/calc/parser.py)                            │
│                                                          │
│  Recursive descent over grammar:                         │
│    expr → term (('+' | '-') term)*                       │
│    term → factor (('*' | '/') factor)*                   │
│    factor → unary                                        │
│    unary → '-' unary | primary                           │
│    primary → NUMBER | '(' expr ')'                       │
│  Produces: AST (BinaryOp, UnaryOp, Number nodes)         │
└────────────────────┬─────────────────────────────────────┘
                     │ AST
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Evaluator  (src/calc/evaluator.py)                      │
│                                                          │
│  Tree-walk evaluation → float64 result                   │
│  Division-by-zero check before divide                    │
│  Overflow check (math.isinf) after each operation        │
└────────────────────┬─────────────────────────────────────┘
                     │ float result or CalcError
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Formatter  (src/calc/evaluator.py or __main__.py)       │
│                                                          │
│  whole-number → str(int(result))                         │
│  fractional   → str with no trailing zeros               │
└────────────────────┬─────────────────────────────────────┘
                     │ string
                     ▼
              stdout (exit 0) or stderr (exit 1)
```

### Data Flow

1. `__main__.py` validates `sys.argv`: 0 args → print usage + exit 1; >1 arg → `error: expected a single quoted expression` + exit 1; empty string → `error: empty expression` + exit 1.
2. The raw expression string is passed to `Lexer(input)`.
3. The `Parser` calls `lexer.nextToken()` on demand (pull model). It builds an AST or raises a `CalcError`.
4. The `Evaluator` tree-walks the AST and returns a `float` or raises a `CalcError`.
5. `__main__.py` formats the result and writes to stdout, or catches any `CalcError`, writes `error: <message>` to stderr, and exits 1.

### Key Design Decisions

| Decision | Rationale | Research reference |
|---|---|---|
| Python implementation | CI already uses `uv run pytest`; stdlib covers all requirements | `testing-strategy.md`, `07-project-layout-makefile-conventions.md` |
| Recursive descent parser | Zero deps; each grammar rule is one function; additive extension path for functions and variables | `parser-architecture.md` |
| Explicit AST (not direct eval) | Clean separation of parse from evaluate; evaluator is independently testable; AST is required for future variable binding | `parser-architecture.md` |
| `float64` as sole numeric type | Single type handles all spec cases; `isinf` detects overflow; `isclose`-to-integer check strips `.0` | `numeric-representation.md` |
| `CalcError` enum / exception hierarchy | One error class per variant; error messages defined in one place; layers return errors, never write to stderr | `04-error-taxonomy-and-exit-codes.md` |
| Lazy/pull lexer | No intermediate token list allocation; parser calls `nextToken()` on demand | `lexer-design.md` |
| `src/` layout with `uv` | Modern PyPA convention; `uv sync --frozen` gives reproducible envs on both platforms | `07-project-layout-makefile-conventions.md` |

---

## Module Breakdown

### Module: cli

**Responsibility**: Parse `sys.argv`, enforce argument-count rules, dispatch to the pipeline, format output, and own all stderr writes and process exit codes.

**Key interfaces**:
- `main()` — entry point called by `__main__.py` and the `[project.scripts]` console script
- Calls `Lexer`, `Parser`, `Evaluator`, `format_result`
- Writes to `sys.stdout` / `sys.stderr`; calls `sys.exit`

**Files**: `src/calc/__main__.py`

**Dependencies**: `lexer`, `parser`, `evaluator`

---

### Module: lexer

**Responsibility**: Tokenize a raw expression string into a stream of typed tokens.

**Key interfaces**:
- `Lexer(input: str)` — constructor
- `Lexer.next_token() -> Token` — returns the next token (pull model)
- `Token(type: TokenType, value: str)` — data class
- `TokenType` enum: `NUMBER`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `LPAREN`, `RPAREN`, `EOF`, `UNKNOWN`
- Raises `CalcError(UnexpectedToken)` on `UNKNOWN` token (or defers to parser — see Open Questions)

**Files**: `src/calc/lexer.py`

**Dependencies**: none (no other calc modules)

---

### Module: parser

**Responsibility**: Consume a token stream from the lexer and produce an AST, enforcing grammar and operator precedence.

**Key interfaces**:
- `Parser(lexer: Lexer)` — constructor
- `Parser.parse() -> ASTNode` — returns the root node or raises `CalcError`
- AST node types: `Number(value: float)`, `BinaryOp(op, left, right)`, `UnaryOp(op, operand)`
- Raises `CalcError(UnexpectedEnd)` and `CalcError(UnexpectedToken)` on syntax errors

**Files**: `src/calc/parser.py`

**Dependencies**: `lexer`

---

### Module: evaluator

**Responsibility**: Tree-walk the AST and compute a numeric result, detecting division by zero and overflow.

**Key interfaces**:
- `evaluate(node: ASTNode) -> float` — raises `CalcError(DivisionByZero)` or `CalcError(Overflow)` on arithmetic errors
- `format_result(value: float) -> str` — returns `"5"` for `5.0`, `"2.5"` for `2.5`

**Files**: `src/calc/evaluator.py`

**Dependencies**: `parser` (for AST node types)

---

### Module: errors

**Responsibility**: Define the `CalcError` exception hierarchy and the canonical error-message mapping.

**Key interfaces**:
- `CalcError` base exception
- Subclasses / variants: `UnexpectedToken`, `UnexpectedEnd`, `DivisionByZero`, `Overflow`, `EmptyExpression`, `ExpectedSingleArg`
- `error_message(e: CalcError) -> str` — returns the verbatim `error: <description>` string for each variant

**Files**: `src/calc/errors.py`

**Dependencies**: none

---

## Cross-Cutting Concerns

### Error Handling Strategy

All errors are represented as `CalcError` subclass instances. Layers (lexer, parser, evaluator) raise errors; they never write to stderr. `__main__.py` is the single owner of stderr output:

```
main
 ├─ arg checks              → raise CalcError subclass
 ├─ Lexer.next_token()      → raise UnexpectedToken
 ├─ Parser.parse()          → raise UnexpectedEnd | UnexpectedToken
 ├─ evaluate(ast)           → raise DivisionByZero | Overflow
 └─ except CalcError as e:
      print(error_message(e), file=sys.stderr)
      sys.exit(1)
```

The `error_message()` function in `errors.py` is the single source of truth for all error strings. Test assertions use it directly to avoid string duplication.

### Testing Approach

Three layers (see `testing-strategy.md`):

1. **Lexer unit tests** (`tests/test_lexer.py`) — assert token lists for all input classes including edge cases (leading dot, trailing dot, unknown chars).
2. **Parser/evaluator unit tests** (`tests/test_parser.py`, `tests/test_evaluator.py`) — assert AST structure and numeric results; assert correct `CalcError` subclass for all error cases; `format_result()` tested independently.
3. **CLI integration tests** (`tests/test_cli.py`) — `subprocess.run` against `python -m calc`; assert exact stdout/stderr strings and exit codes for all 10 spec success criteria.

All tests run via `make test` → `uv run pytest tests/ -v` on both macOS and Linux.

### Configuration and Environment

No configuration files. All input arrives via `sys.argv[1]`. Build and test environment is fully described by `pyproject.toml` and `uv.lock`. `make build` runs `uv sync --frozen` to guarantee a reproducible virtualenv.

### Observability / Logging

No logging framework. The tool is a single-shot CLI; the only observable output is one line to stdout (success) or one line to stderr (failure). No log files, no debug output unless a future spec revision adds a `--verbose` flag.

---

## Open Questions

1. **UNKNOWN token handling boundary**: Research (`lexer-design.md`) leaves open whether the lexer emits `UNKNOWN` tokens for the parser to handle, or raises immediately. The LLD for `lexer` should decide: raising immediately is simpler; emitting allows the parser to report the offending character in context. Either option is valid for v0.1.0.

2. **`format_result` location**: The formatter is a pure function; it could live in `evaluator.py` or be a standalone utility. The LLD for `evaluator` should decide its exact placement.

3. **AST node representation**: Python dataclasses, named tuples, or plain classes are all viable. The LLD for `parser` should specify the exact representation to keep `evaluator.py` imports clear.

4. **`NaN` handling**: `0.0 / 0.0` in IEEE 754 yields NaN, not Inf. The evaluator's overflow check uses `math.isinf`; a separate `math.isnan` guard may be needed. The LLD for `evaluator` should specify whether NaN maps to `Overflow` or a distinct error.
