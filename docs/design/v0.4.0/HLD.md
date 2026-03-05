# High-Level Design — Calculator v0.4.0 (User-Defined Functions)

**Milestone:** v0.4.0
**Date:** 2026-03-05
**Status:** Draft

---

## System Overview

The calculator is a single-binary command-line tool (`calc`) that accepts one arithmetic
expression — or a semicolon-separated sequence of statements — as a shell argument,
evaluates them in order, and prints the result of the last expression statement to stdout.
It targets developers who want quick, scriptable calculations without leaving the terminal.
The implementation is in Python and ships with no external runtime dependencies beyond the
Python standard library.

The pipeline has four stages: the **Lexer** tokenises the raw input string; the **Parser**
consumes the token stream and builds an explicit AST rooted at a `Program` node; the
**Evaluator** executes each statement in order, maintaining a mutable variable environment
and a separate mutable function environment; and the **Formatter** converts the final
`float` result to a clean string for stdout. All errors are represented as `CalcError`
subclass instances and are caught at the CLI boundary, which is the sole owner of stderr
writes and process exit codes.

The codebase has five modules: `cli` (`__main__.py`), `lexer`, `parser`, `evaluator`, and
`errors`. They form a strict dependency chain: cli → evaluator → parser → lexer; `errors`
has no dependencies.

In v0.4.0 the language is extended with **user-defined single-expression functions**.
A user writes `def name(params) = expression` to bind a named formula, and calls it with
`name(args)` exactly as they call built-in functions. Function bodies may reference their
own parameters, named constants (`pi`, `e`), built-in functions, and any user-defined
function defined earlier in the same statement sequence. Function bodies may not reference
outer variables from the enclosing statement sequence. Functions defined later in the
sequence are not visible to earlier functions (no forward references). These semantics are
enforced at definition time by taking a snapshot of the current function environment and
storing it inside the function object.

The `UserFunction` type stores `params` and a parsed AST body — never a Python callable —
satisfying the spec requirement that function definitions be representable as serializable
values without redesigning the runtime. The serialization layer itself is not shipped in
this version; only the serialization-compatible data model is established.

**Key constraints:**
- Single-argument invocation: `calc '<expression-or-program>'`
- Runs on macOS and Linux with no external runtime dependencies beyond stdlib
- `make test` must pass clean on both platforms
- Completes any valid expression in under 100 ms
- `def` is a reserved keyword; it cannot be used as a variable name
- Variables and functions are stored in separate namespaces; a variable and a function may
  share the same name without collision
- Function bodies are single expressions — no multi-statement bodies, no local variables
- Recursive functions are not supported; the forward-reference prohibition makes direct
  recursion impossible by construction
- Named constants `pi` and `e` are read-only; reassignment raises an error
- All v0.1.x, v0.2.x, and v0.3.x behaviour is preserved unchanged

**Non-goals:**
- Recursive functions
- Multi-statement function bodies with local variables
- Closures (function bodies do not capture outer variables)
- Persistent REPL mode
- Windows support

---

## Architecture

### Top-level component diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│  CLI Entry Point  (__main__.py)                                        │
│                                                                        │
│  1. Parse argv                                                         │
│  2. Lex + parse → Program node                                         │
│  3. Initialise env: dict[str, float] and fn_env: dict[str,UserFunction]│
│  4. For each Statement in Program.body:                                │
│        result = execute_statement(stmt, env, fn_env)                   │
│  5. Print result of last expression statement (if any)                 │
└──────────────────┬────────────────────────────────┬────────────────────┘
                   │ Lexer(source)                   │ execute_statement(stmt, env, fn_env)
                   ▼                                 ▼
┌──────────────────────────┐       ┌──────────────────────────────────────┐
│  Lexer  (lexer.py)       │       │  Evaluator  (evaluator.py)           │
│                          │       │                                      │
│  TokenType +             │       │  evaluate(node, env, fn_env) → float │
│    DEF (new)             │       │                                      │
│  Token stream            │       │  execute_statement(stmt, env, fn_env)│
└──────────────────────────┘       │    → float | None                    │
                   │               │                                      │
                   ▼               │  UserFunction dataclass (new)        │
┌──────────────────────────┐       │  _CONSTANTS_VALUES: dict (new)       │
│  Parser  (parser.py)     │       │  _CONSTANTS: frozenset               │
│                          │       │  _DEFAULT_ENV: MappingProxy          │
│  parse_program()         │       │  _FUNCTION_TABLE: dict               │
│   → Program              │       └──────────────────────────────────────┘
│  FunctionDef (new)       │
│  Statement =             │       ┌──────────────────────────────────────┐
│   Assignment             │       │  Errors  (errors.py)                 │
│   | FunctionDef (new)    │       │                                      │
│   | ASTNode              │       │  FunctionAlreadyDefined (new)        │
└──────────────────────────┘       │  CannotRedefineBuiltin (new)         │
                                   │  UnknownFunction (message updated)   │
                                   │  WrongArity (message updated)        │
                                   └──────────────────────────────────────┘
```

### Data flow

```
argv[1]
  │
  ▼
Lexer.next_token()  ──►  Token stream (DEF token now included)
  │
  ▼
Parser.parse_program()  ──►  Program(body=[stmt, stmt, ...])
                              stmt = Assignment | FunctionDef | ASTNode
  │
  ▼  (iterate Program.body)
execute_statement(stmt, env, fn_env)
  │
  ├─ Assignment:
  │   evaluate(stmt.value, env, fn_env) → float
  │   check _CONSTANTS → ConstantReassignment?
  │   env[stmt.name] = float
  │   return float
  │
  ├─ FunctionDef:                          ← NEW in v0.4.0
  │   check _FUNCTION_TABLE → CannotRedefineBuiltin?
  │   check fn_env → FunctionAlreadyDefined?
  │   walk body AST for Call nodes → undefined call → UnknownFunction?
  │   fn_env[stmt.name] = UserFunction(
  │       name=stmt.name,
  │       params=stmt.params,
  │       body=stmt.body,
  │       available_fns=dict(fn_env)  # snapshot at definition time
  │   )
  │   return None
  │
  └─ ASTNode:
      evaluate(stmt, env, fn_env) → float
      return float

evaluate(node, env, fn_env):
  ├─ Number      → node.value
  ├─ BinaryOp    → evaluate(left) OP evaluate(right)
  ├─ UnaryOp     → -evaluate(operand)
  ├─ Name        → env[node.name] or UndefinedVariable
  └─ Call        →
      if node.func in _FUNCTION_TABLE:
          built-in path (unchanged)
      elif node.func in fn_env:          ← NEW
          uf = fn_env[node.func]
          check arity → WrongArity?
          body_env = dict(_CONSTANTS_VALUES) + {param: arg_value, ...}
          return evaluate(uf.body, body_env, uf.available_fns)
      else:
          raise UnknownFunction(node.func)
  │
  ▼
result of last expression statement  ──►  format_result()  ──►  stdout
```

### Key design decisions

| Decision | Choice | Research basis |
|---|---|---|
| Python implementation | CI already uses `uv run pytest`; stdlib covers all requirements | `testing-strategy.md`, `07-project-layout-makefile-conventions.md` |
| Recursive descent parser | Zero deps; each grammar rule is one function; additive extension path | `parser-architecture.md` |
| Explicit AST (not direct eval) | Clean separation of parse from evaluate; evaluator is independently testable | `parser-architecture.md` |
| `float64` as sole numeric type | Single type handles all spec cases; `isinf` detects overflow | `numeric-representation.md` |
| `CalcError` exception hierarchy | One error class per variant; error messages defined in one place | `04-error-taxonomy-and-exit-codes.md` |
| Lazy/pull lexer | No intermediate token list allocation; parser calls `next_token()` on demand | `lexer-design.md` |
| `src/` layout with `uv` | Modern PyPA convention; `uv sync --frozen` gives reproducible envs | `07-project-layout-makefile-conventions.md` |
| Single `IDENT` token type for most identifiers | Lexer stays context-free for non-keyword identifiers | #38, #43, #53, #73 |
| `DEF` as a reserved `TokenType` variant | Type-safe dispatch in parser; no string comparisons; extensible keyword table; zero regression risk (no existing tests use `def` as a variable) | Research #153 |
| Keyword table in `_scan_ident` | One-line extension path for future keywords (`let`, `return`, etc.) | Research #153 |
| `FunctionDef` AST node mirrors `Assignment` | Consistent dataclass pattern: `name`, `params`, `body`; statement-level only | Research #156, #158 |
| `Statement` union extended to include `FunctionDef` | `Statement = Assignment \| FunctionDef \| ASTNode` | Research #156 |
| Split stores: `env: dict[str, float]` + `fn_env: dict[str, UserFunction]` | Type safety; no union narrowing at lookup; scoping semantics fall out naturally (body eval receives restricted env) | Research #154 |
| `UserFunction` stores `params`, `body: ASTNode`, `available_fns` snapshot | Not a `Callable`; serialization-compatible by construction; snapshot enforces forward-reference prohibition structurally | Research #154, #156, #157 |
| Function body scoped to params + constants only (no outer vars) | Spec requirement; enforced by building a fresh `body_env` from `_CONSTANTS_VALUES` + param bindings only | Research #157 |
| `_CONSTANTS_VALUES: dict[str, float]` alongside `_CONSTANTS: frozenset` | Avoids duplicating float values; both top-level `_DEFAULT_ENV` and per-call `body_env` derive from it | Research #157 |
| Snapshot `fn_env` at definition time | Makes `UserFunction` self-describing; forward-reference prohibition guaranteed structurally without ordering checks at call time | Research #154, #157 |
| Recursion prevention at definition time (AST walk) | Body AST is walked for `Call` nodes when `def` is executed; any call to a name not in the current snapshot raises `UnknownFunction`; no runtime cycle detection needed | Research #157 |
| No lookahead added for `def` dispatch | `DEF` token is unambiguous at position 0 of `_parse_statement`; LL(1) maintained | Research #158 |
| Dedicated `_parse_param_list()` (not reusing `_parse_arglist()`) | Params are bare `IDENT`s, not expressions; reusing `_parse_arglist` would accept invalid syntax | Research #158 |
| `execute_statement` return type `float \| None` | `def` statements have no numeric result; `None` signals "no output for this statement" | Research #154 |
| Modify `UnknownFunction.description()` and `WrongArity.description()` in place | New v0.4.0 wording is more consistent with the rest of the error vocabulary; only three test assertions require updating | Research #155 |
| Add `FunctionAlreadyDefined` and `CannotRedefineBuiltin` as sibling classes | Semantically distinct from each other and from `UnknownFunction`; follow `UndefinedVariable`/`ConstantReassignment` pattern | Research #155 |
| Extend existing per-layer test files (not a new `test_functions.py`) | Preserves one-file-per-layer discipline; no infrastructure duplication | Research #159 |
| Individual named `test_` functions in `test_cli.py` | Failure messages are self-documenting; heterogeneous assertion structure doesn't fit `parametrize` | Research #159 |
| `COMMA` as first-class `TokenType` | Consistent with every other syntactically meaningful single-char token | #65 |
| `Name` AST node (eval-time lookup) | Parser stays table-agnostic; same node type serves user variables, constants | #43, #56 |
| Separate `_DEFAULT_ENV` and `_FUNCTION_TABLE` | Grammar disambiguates (`IDENT LPAREN` → `Call`; bare `IDENT` → `Name`) | #39, #43, #56 |
| `FunctionEntry` dataclass with `domain_check` predicate | Domain constraints co-located with function entry; explicit, independently testable | #39, #40, #54 |
| `_round_half_away` helper | Python 3 `round()` uses banker's rounding; spec requires round-half-away-from-zero | #41, #75 |
| `str(value)` in `format_result` decimal branch | Shortest round-trip string; matches all spec-mandated decimal outputs | #44, #57 |
| `description()` method on `CalcError` | Parameterized errors cannot use a static dict; method dispatch is uniform | #55, #68 |
| Lookahead strategy | 2-token window (`_lookahead` slot, lazy) | #110 Option A |
| Trailing semicolons accepted | Consistent with v0.3.0 | #110 Q3 |
| `_DEFAULT_ENV` safety | `MappingProxyType`; fresh copy per invocation | #114 Q4 |

---

## Module Breakdown

### Module: lexer

**Responsibility:** Convert a raw source string into a flat token stream, recognising
`def` as a reserved keyword distinct from ordinary identifiers.

**Key interfaces:**
- `TokenType` enum — `NUMBER`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `LPAREN`, `RPAREN`,
  `EOF`, `UNKNOWN`, `IDENT`, `COMMA`, `SEMICOLON`, `EQUALS`, `DEF` (14 types total;
  `DEF` is new in v0.4.0)
- `Token(type: TokenType, value: str)` dataclass
- `Lexer(source: str)` class with `next_token() → Token`
- Module-level `_KEYWORDS: dict[str, TokenType]` — maps `"def"` to `TokenType.DEF`;
  extensible for future keywords with no parser changes required

**Files:** `src/calc/lexer.py`

**Dependencies:** none (stdlib only)

---

### Module: parser

**Responsibility:** Consume a token stream from `Lexer` and produce a typed AST rooted
at a `Program` node, including recognition and structuring of function definition
statements.

**Key interfaces:**
- `ASTNode` union type alias: `Number | BinaryOp | UnaryOp | Name | Call`
- `Number(value: float)` — numeric literal
- `BinaryOp(op: str, left: ASTNode, right: ASTNode)` — binary arithmetic
- `UnaryOp(op: str, operand: ASTNode)` — unary minus
- `Name(name: str)` — bare identifier (variable or constant lookup)
- `Call(func: str, args: list[ASTNode])` — function call (built-in or user-defined)
- `Assignment(name: str, value: ASTNode)` — variable assignment statement
- `FunctionDef(name: str, params: list[str], body: ASTNode)` — function definition
  statement (new in v0.4.0)
- `Program(body: list[Statement])` — sequence of statements (top-level root)
- `Statement = Assignment | FunctionDef | ASTNode` type alias (extended in v0.4.0)
- `Parser(lexer: Lexer)` class with `parse_program() → Program`
- Internal methods: `_parse_statement()`, `_parse_funcdef()` (new), `_parse_param_list()`
  (new), `_parse_arglist()`, `_parse_expr()`, `_peek_next()`

**Files:** `src/calc/parser.py`

**Dependencies:** `lexer` (TokenType, Lexer, Token)

---

### Module: evaluator

**Responsibility:** Walk the AST recursively and produce a `float` result; maintain a
mutable variable environment and a separate mutable function environment across statement
execution; store user-defined functions; enforce scoping, arity, domain, constant-
reassignment, duplicate-function, and forward-reference constraints; detect overflow.

**Key interfaces:**
- `UserFunction(name: str, params: list[str], body: ASTNode, available_fns: dict[str, "UserFunction"])` — frozen dataclass; stores AST body (not a `Callable`)
- `evaluate(node: ASTNode, env: dict[str, float], fn_env: dict[str, UserFunction] | None = None) → float`
- `execute_statement(stmt: Statement, env: dict[str, float], fn_env: dict[str, UserFunction]) → float | None`
- `format_result(value: float) → str` — `"5"` for whole results, `str(value)` for decimals
- `_DEFAULT_ENV: MappingProxyType[str, float]` — built-in constants (`pi`, `e`); never mutated
- `_CONSTANTS_VALUES: dict[str, float]` — `{"pi": math.pi, "e": math.e}`; used to build function body envs (new in v0.4.0)
- `_CONSTANTS: frozenset[str]` — names that may not be reassigned
- `_FUNCTION_TABLE: dict[str, FunctionEntry]` — 12 built-in functions

**Files:** `src/calc/evaluator.py`

**Dependencies:** `parser` (ASTNode, Assignment, FunctionDef), `errors` (all CalcError subclasses), `math` (stdlib)

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
- `UnknownFunction(name)` — message updated to `"undefined function: <name>"` (no quotes; v0.4.0)
- `WrongArity(name, expected)` — message updated to `"wrong number of arguments: <name> expects <N> argument[s]"` (v0.4.0)
- `DomainError()` — argument outside function's mathematical domain
- `UndefinedVariable(name: str)` — `Name` node not found in env
- `ConstantReassignment(name: str)` — attempt to assign to a read-only constant
- `FunctionAlreadyDefined(name: str)` — duplicate `def` for the same name (new in v0.4.0)
- `CannotRedefineBuiltin(name: str)` — `def` targeting a built-in function name (new in v0.4.0)
- `error_message(e: CalcError) → str` — returns `"error: <e.description()>"`

**Files:** `src/calc/errors.py`

**Dependencies:** none

---

### Module: cli

**Responsibility:** Parse CLI arguments, drive the lex → parse → execute pipeline,
thread both `env` and `fn_env` through the statement loop, format output to stdout/stderr,
and set the exit code.

**Key interfaces:**
- `main()` entry point called from `__main__.py`
- Initialises `env: dict[str, float] = dict(_DEFAULT_ENV)` and
  `fn_env: dict[str, UserFunction] = {}`
- Iterates `Program.body`, calling `execute_statement(stmt, env, fn_env)` per statement
- Tracks last non-`None` result; prints it on completion (integer if whole, decimal
  otherwise); if all statements are `def` (last result is `None`), no output is written

**Files:** `src/calc/__main__.py`

**Dependencies:** `lexer`, `parser`, `evaluator`, `errors`

---

## Cross-Cutting Concerns

### Error handling strategy

All errors descend from `CalcError`. The CLI catches `CalcError`, writes
`"error: " + e.description()` to stderr, and exits 1. No error type is swallowed
silently.

New error conditions in v0.4.0:

- `FunctionAlreadyDefined` — raised by `execute_statement()` when a `FunctionDef`
  statement names a function already in `fn_env`.
- `CannotRedefineBuiltin` — raised by `execute_statement()` when a `FunctionDef`
  names a function already in `_FUNCTION_TABLE`.
- Forward-reference errors — when the body AST of a new `FunctionDef` is walked,
  any `Call` node whose name is not in the current `fn_env` snapshot raises
  `UnknownFunction`. This is raised at definition time, not call time.

Updated error messages (v0.4.0 wording change; affects three existing test assertions):

- `UnknownFunction.description()` → `"undefined function: <name>"` (was: `"unknown function '<name>'"`)
- `WrongArity.description()` → `"wrong number of arguments: <name> expects <N> argument[s]"` (was: `"'<name>' expects <N> argument[s]"`)

All v0.2.x arithmetic errors (`DivisionByZero`, `DomainError`, `Overflow`) and v0.3.x
variable errors (`UndefinedVariable`, `ConstantReassignment`) propagate unchanged.

### Testing approach

- Unit tests per module (`test_lexer.py`, `test_parser.py`, `test_evaluator.py`,
  `test_errors.py`) — each existing file gains a clearly marked `# v0.4.0 —
  user-defined functions` block with new test cases for that layer.
- No new top-level test file is introduced; the one-file-per-layer discipline is
  preserved (research #159).
- `test_lexer.py`: assert `DEF` token emission; confirm `define`/`default` still emit
  `IDENT`.
- `test_parser.py`: assert `FunctionDef` node shape for zero, one, and multiple
  params; assert `Call` still works in expression position.
- `test_evaluator.py`: test `execute_statement(FunctionDef(...), env, fn_env)` via
  hand-constructed AST nodes (unit coverage); add one `eval_expr` integration case
  (full parse+evaluate path). Use `@pytest.mark.parametrize` only for homogeneous
  arithmetic cases; use individual named functions for heterogeneous paths (arity
  errors, forward-reference errors).
- `test_errors.py`: update three existing assertions for the changed
  `UnknownFunction` and `WrongArity` messages; add new assertions for
  `FunctionAlreadyDefined` and `CannotRedefineBuiltin`.
- `test_cli.py`: add one named `test_` function per spec success criterion (12
  functions) plus named functions for each failure mode (≥4 functions), following
  the existing `test_variable_assignment` naming convention.
- Regression: all v0.1.x–v0.3.x success criteria must continue to pass; the
  only necessary changes to existing tests are the three message-string updates
  in `test_errors.py`.

### Configuration and environment

- No configuration files; all behaviour is determined by CLI arguments.
- `_DEFAULT_ENV` and `_CONSTANTS_VALUES` are module-level constants in
  `evaluator.py` — the single source of truth for built-in constant values.
- Fresh `dict(_DEFAULT_ENV)` and `{}` are created per invocation for `env` and
  `fn_env` respectively — no mutable global state.
- `_CONSTANTS_VALUES` is used directly to seed the restricted environment passed
  to function body evaluation.

### Observability / logging

No logging in v0.4.0. All user-visible output is either the numeric result on
stdout or a `"error: ..."` line on stderr, matching the v0.1.x–v0.3.x contract.

---

## Open Questions

The following decisions are deferred to the LLD for each module:

1. **`lexer` LLD** — Exact placement of `_KEYWORDS` dict (module-level vs class
   constant) and whether `_scan_ident` is refactored into a helper that handles
   both keyword lookup and the look-ahead guard for `e`/`E` in numeric scanning.

2. **`parser` LLD** — Whether `FunctionDef` lives alongside existing nodes in
   `parser.py` or in a separate `ast.py`; exact error raised when `def` is
   followed by a non-`IDENT` token (i.e. `def 5(x) = x`).

3. **`evaluator` LLD** — Exact implementation of the body-AST walk for
   forward-reference detection (recursive function vs itertools traversal); whether
   `_call_user_fn` is extracted as a named helper or inlined in the `Call` branch
   of `evaluate`; exact behaviour when the entire program consists only of `def`
   statements (no output to stdout, exit 0 — confirmed by spec but not explicitly
   tested).

4. **`errors` LLD** — Whether `WrongArity` retains a separate `expected` attribute
   after the message change, and whether `CannotRedefineBuiltin` is a subclass of
   any existing error or a direct subclass of `CalcError`.

5. **`cli` LLD** — Whether `fn_env` is constructed inside `main()` or delegated to
   a factory in `evaluator.py`; exact guard condition for suppressing stdout when
   `last_result is None`.
