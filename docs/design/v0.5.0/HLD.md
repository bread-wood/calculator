# High-Level Design — Calculator v0.5.0 (Renderer)

**Milestone:** v0.5.0
**Date:** 2026-03-05
**Status:** Draft

---

## System Overview

The calculator is a single-binary command-line tool (`calc`) that accepts either an
arithmetic expression or a structured subcommand as its argument. In the expression
mode (all prior versions), it evaluates a semicolon-separated sequence of statements
and prints the result to stdout. In v0.5.0, a new `plot` subcommand is added: given
an expression in a single free variable `x`, `calc plot` samples the expression over
a configurable domain, assembles a device-independent scene representation, and writes
the result as a PNG or SVG image file. The tool targets developers who want a quick
function plot without opening a spreadsheet or Python notebook.

The implementation is in Python and ships with no external runtime dependencies beyond
the Python standard library. PNG output is produced by a hand-rolled encoder using
`struct` and `zlib`; SVG output is produced by string/XML generation. The rendering
pipeline is structured around a shared, immutable `Scene` dataclass so that the same
curve-generation logic can feed a live Tk window in v0.7.x without duplication.

**Key constraints:**
- Single binary; macOS and Linux only; no Windows in this version
- No external runtime dependencies beyond the Python standard library and CPython
  built-in modules
- No display or windowing system required at runtime; all output is written to file
- Sampling resolution must be at least 1 sample per pixel of output width
- The rendering pipeline must be structured so that the same `Scene` can be rendered
  to a live window in v0.7.x without modifying the curve-generation layer
- `make test` must pass clean on macOS and Linux with no display required
- All v0.1.x–v0.4.x expression-evaluation behaviour is preserved unchanged

**Non-goals:**
- Multiple curves on one plot (v0.6.x)
- Parametric curves (v0.6.x)
- Interactive window display (v0.7.x)
- Expression entry in a window (v0.8.x)
- Implicit curves or inequalities (v0.9.x)
- Windows support

---

## Architecture

### Top-level component diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CLI Entry Point  (__main__.py)                                               │
│                                                                               │
│  SUBCOMMANDS = frozenset({"plot"})                                            │
│                                                                               │
│  main():                                                                      │
│    if sys.argv[1] not in SUBCOMMANDS:                                         │
│        _legacy_eval()    ← unchanged expression pipeline from v0.4.x          │
│    else:                                                                      │
│        argparse dispatch → run_plot(args)                                     │
└────────────┬──────────────────────────────┬───────────────────────────────────┘
             │ (legacy path)                │ (plot path)
             ▼                              ▼
┌────────────────────────┐     ┌────────────────────────────────────────────┐
│  Expression Pipeline   │     │  Plot Command  (plot.py)                   │
│                        │     │                                            │
│  Lexer → Parser        │     │  1. Validate args (xmin<xmax, format)      │
│    → Evaluator         │     │  2. Parse expression → AST                 │
│    → format_result     │     │  3. build_scene(expr, xmin, xmax, w, h)   │
│    → stdout            │     │  4. select renderer by file extension      │
└────────────────────────┘     │  5. renderer.render(scene, output_path)   │
                               │  6. handle OSError → OutputWriteError     │
                               └──────────────┬─────────────────────────────┘
                                              │
                               ┌──────────────▼─────────────────────────────┐
                               │  Plotter  (plotter.py)                     │
                               │                                            │
                               │  build_scene(expr, xmin, xmax, w, h)      │
                               │    → sample expression over x_values       │
                               │    → discontinuity detection               │
                               │    → build_segments()                      │
                               │    → compute y-range + 10% padding         │
                               │    → calc_ticks() for x and y              │
                               │    → return Scene(frozen dataclass)        │
                               └──────────────┬─────────────────────────────┘
                                              │ Scene
                               ┌──────────────▼─────────────────────────────┐
                               │  Renderer Package  (renderer/)             │
                               │                                            │
                               │  Renderer Protocol:                        │
                               │    render(scene: Scene, output: Path)→None │
                               │                                            │
                               │  renderer/__init__.py  — dispatch          │
                               │  renderer/png.py  — PngRenderer            │
                               │  renderer/svg.py  — SvgRenderer            │
                               └────────────────────────────────────────────┘

Supporting modules (shared by both paths):
┌──────────────────────────────────────────┐
│  Lexer  (lexer.py)                       │
│  Parser  (parser.py)                     │
│  Evaluator  (evaluator.py)               │
│  Errors  (errors.py)    ← extended v0.5  │
│  PNG encoder  (png.py)  ← new v0.5       │
└──────────────────────────────────────────┘
```

### Data flow

#### Legacy expression path (unchanged from v0.4.x)

```
argv[1]  (not a subcommand keyword)
  │
  ▼
_legacy_eval():
  Lexer(source) → token stream
  Parser.parse_program() → Program(body=[stmt, ...])
  For each stmt: execute_statement(stmt, env, fn_env)
  format_result(last_result) → stdout
```

#### Plot path (new in v0.5.0)

```
argv = ["calc", "plot", "<expr>", --xmin, --xmax, --width, --height, --output]
  │
  ▼
argparse subparser (plot):
  expression: str
  xmin: float = -10, xmax: float = 10
  width: int = 800, height: int = 600
  output: Path = "./plot.png"
  │
  ▼
run_plot(args):
  1. validate: xmin < xmax → InvalidDomainBounds on fail
  2. infer format from output.suffix (.png / .svg) → UnsupportedFormat on unknown
  3. parse expression → AST  (Lexer → Parser; UndefinedFunction / UndefinedVariable on error)
  4. build_scene(ast, xmin, xmax, width, height) → Scene
  5. select renderer: PngRenderer or SvgRenderer
  6. renderer.render(scene, output_path) → write file; OSError → OutputWriteError
  7. exit 0
  │
  ▼
build_scene(ast, xmin, xmax, width, height):
  x_values = linspace(xmin, xmax, n=width)         # ≥1 sample per pixel
  raw = sample_expression(ast, x_values)            # list of (x, y|None)
    ├─ evaluate(ast, {"x": xi, **_CONSTANTS_VALUES}) per point
    └─ CalcError → mark None (gap)
  slope-jump heuristic:
    diffs = |y[i+1]-y[i]| for consecutive valid pairs
    threshold = max(10 × median(diffs), 1e-12)
    mark left sample None when |Δy| > threshold
  segments = build_segments(raw)                    # list[list[(x,y)]]
  if sum(len(s) for s in segments) == 0:
    raise DomainEmpty
  y_valid = all valid y values across segments
  y_min, y_max = min(y_valid) − 10%span, max(y_valid) + 10%span
  x_ticks = calc_ticks(xmin, xmax)                 # Heckbert nice-numbers
  y_ticks = calc_ticks(y_min, y_max)
  return Scene(width, height, xmin, xmax, y_min, y_max,
               x_ticks, y_ticks, segments)
  │
  ▼
PngRenderer.render(scene, output):
  pixels = [background_color] × (width × height)
  draw axis lines (x=0, y=0 if in range)
  draw tick marks at Scene tick positions
  for segment in scene.segments:
    draw polyline between consecutive (x,y) sample pairs
    (world→pixel: px = (x-x_min)/(x_max-x_min)*width,
                  py = (y_max-y)/(y_max-y_min)*height)
  png_bytes = encode_png(width, height, pixels)     # struct+zlib only
  output.write_bytes(png_bytes)

SvgRenderer.render(scene, output):
  root = <svg width height xmlns>
  draw axis lines as <line> elements
  draw tick marks + labels as <line>/<text> elements
  for segment in scene.segments:
    emit <polyline points="x1,y1 x2,y2 ..."/>
  output.write_text(ET.tostring(root, ...))
```

### Key design decisions

| Decision | Choice | Research basis |
|---|---|---|
| Single `Scene` dataclass as IR | World-space, immutable, renderer-agnostic; serves PNG, SVG, and future Tk window from the same data | Research #166 |
| `plotter.py` has no renderer imports | CLI instantiates the correct renderer; plotter only produces `Scene`; v0.7.x adds `renderer/tk.py` with zero changes to plotter | Research #166 |
| PNG via hand-rolled `struct`+`zlib` encoder | "stdlib image/graphics packages" means CPython stdlib only; Pillow is third-party and excluded; 25-line encoder covers 8-bit RGB, no interlace, filter=None | Research #167 |
| SVG via `xml.etree.ElementTree` / f-strings | SVG is plain XML text; zero dependency tension | Research #167 |
| No Pillow in any `pyproject.toml` section | Runtime: spec-forbidden. Dev: production code cannot import a dev-only dep. Optional extra: degrades UX and complicates CI | Research #167 |
| `argparse` subparsers + early-exit legacy branch | Five typed flags for `plot` make manual parsing error-prone; `argparse` is stdlib; early-exit at `sys.argv[1]` check preserves `calc '<expr>'` unchanged without argparse hacks | Research #168 |
| `SUBCOMMANDS = frozenset({"plot"})` sentinel | Extensible for v0.6.x/v0.7.x by adding one string; no argparse needed for legacy path | Research #168 |
| Exception-based gap detection | Catches `DivisionByZero`/`DomainError`/`Overflow` per sample; handles `1/x`, `sqrt(x<0)`, `log(x≤0)` | Research #169 |
| Slope-jump heuristic (K=10 × median Δy) | Catches finite-valued asymptotes (`tan(x)` near π/2); K=10 safe against false positives on smooth curves including `x^3`; median avoids inflation by outliers; `max(threshold, 1e-12)` guards flat functions | Research #169 |
| Segment-list IR for gaps | Renderers draw each polyline independently; no gap-marker post-processing; natural for multi-curve in v0.6.x | Research #169 |
| `DomainEmpty` error after sampling | Raised when zero valid samples remain; covers `sqrt(x)` over all-negative domain and `1/0` constant | Research #169 |
| New `UndefinedFunction` class (not modifying `UnknownFunction`) | Spec mandates `"undefined function: <name>"` format; `UnknownFunction` uses `"unknown function '<name>'"` with different verb, separator, and quoting; changing it breaks existing tests | Research #170 |
| Reuse `UndefinedVariable` unchanged | Format already matches spec exactly: `"undefined variable: <name>"` | Research #170 |
| `OutputWriteError`, `UnsupportedFormat`, `DomainEmpty`, `InvalidDomainBounds` as new `CalcError` subclasses | Keeps error path uniform (raise → `error_message()` → stderr → exit 1); all added to existing `errors.py` | Research #170 |
| Scene IR inspection as primary test strategy | Mathematical invariants are cross-platform, display-free, renderer-agnostic; fast unit-test speed | Research #171 |
| PNG pixel sampling via IDAT decompression | Verifies renderer coordinate transform; uses only `struct`+`zlib` (stdlib); reads pixel at `(col, row)` from decompress scanlines | Research #171 |
| SVG tests via `xml.etree.ElementTree` | Structural assertions on `<polyline>`/`<path>` elements; stable across rendering changes | Research #171 |
| No golden-file / snapshot tests | PNG bytes differ between macOS and Linux due to `zlib` compression; human review required for regeneration; too fragile for cross-platform CI | Research #171 |
| Heckbert nice-numbers tick algorithm (1990), target 6 ticks | Industry standard (used in Matplotlib, D3, gnuplot); handles all edge cases (straddle-zero, small range, constant-value) with ~30 lines; no external library | Research #172 |
| `{:.3g}` tick label format | Strips trailing zeros; uses scientific notation for very large/small values; handles all spec cases without special-casing | Research #172 |
| Python implementation | CI already uses `uv run pytest`; stdlib covers all v0.5.0 requirements | v0.4.0 HLD |
| Recursive descent parser | Zero deps; each grammar rule is one function; additive extension path | v0.4.0 HLD |
| Explicit AST | Clean separation of parse from evaluate | v0.4.0 HLD |
| `float64` sole numeric type | Handles all spec cases; `isinf` detects overflow | v0.4.0 HLD |
| `CalcError` exception hierarchy | One error class per variant; uniform error path | v0.4.0 HLD |
| Lazy/pull lexer | No intermediate token list; parser calls `next_token()` on demand | v0.4.0 HLD |
| `src/` layout with `uv` | Modern PyPA convention; reproducible envs | v0.4.0 HLD |
| `DEF` as reserved `TokenType` | Type-safe dispatch; extensible keyword table | v0.4.0 HLD |
| Split `env`/`fn_env` stores | Type safety; scoping semantics for user-defined functions | v0.4.0 HLD |
| `UserFunction` stores AST body + `available_fns` snapshot | Serialization-compatible; forward-reference prohibition guaranteed structurally | v0.4.0 HLD |

---

## Module Breakdown

### Module: lexer

**Responsibility:** Convert a raw source string into a flat token stream, recognising
`def` as a reserved keyword distinct from ordinary identifiers.

**Key interfaces:**
- `TokenType` enum — `NUMBER`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `LPAREN`, `RPAREN`,
  `EOF`, `UNKNOWN`, `IDENT`, `COMMA`, `SEMICOLON`, `EQUALS`, `DEF` (14 types)
- `Token(type: TokenType, value: str)` dataclass
- `Lexer(source: str)` class with `next_token() → Token`
- `_KEYWORDS: dict[str, TokenType]` — maps `"def"` → `TokenType.DEF`

**Files:** `src/calc/lexer.py`

**Dependencies:** none

---

### Module: parser

**Responsibility:** Consume a token stream from `Lexer` and produce a typed AST rooted
at a `Program` node, including recognition and structuring of variable assignment and
user-defined function definition statements.

**Key interfaces:**
- `ASTNode` union: `Number | BinaryOp | UnaryOp | Name | Call`
- `Assignment(name: str, value: ASTNode)`
- `FunctionDef(name: str, params: list[str], body: ASTNode)`
- `Program(body: list[Statement])`
- `Statement = Assignment | FunctionDef | ASTNode`
- `Parser(lexer: Lexer)` with `parse_program() → Program`

**Files:** `src/calc/parser.py`

**Dependencies:** `lexer`

---

### Module: evaluator

**Responsibility:** Walk the AST recursively and produce a `float` result; maintain
mutable variable and function environments across statement execution; enforce scoping,
arity, domain, constant-reassignment, duplicate-function, and forward-reference
constraints; expose constants for use in the plot path.

**Key interfaces:**
- `UserFunction(name, params, body, available_fns)` frozen dataclass
- `evaluate(node: ASTNode, env: dict[str, float], fn_env: dict[str, UserFunction] | None) → float`
- `execute_statement(stmt, env, fn_env) → float | None`
- `format_result(value: float) → str`
- `_DEFAULT_ENV: MappingProxyType[str, float]` — built-in constants
- `_CONSTANTS_VALUES: dict[str, float]` — `{"pi": math.pi, "e": math.e}`
- `_CONSTANTS: frozenset[str]`
- `_FUNCTION_TABLE: dict[str, FunctionEntry]`

**Files:** `src/calc/evaluator.py`

**Dependencies:** `parser`, `errors`, `math`

---

### Module: errors

**Responsibility:** Define the public `CalcError` hierarchy; provide human-readable
error descriptions via `description()` methods; cover all error conditions from
expression evaluation and the plot command.

**Key interfaces:**
- `CalcError(Exception)` — base class with abstract `description() → str`
- `error_message(e: CalcError) → str` — returns `"error: <e.description()>"`
- Expression errors (v0.1.x–v0.4.x): `ExpectedSingleArg`, `EmptyExpression`,
  `UnexpectedToken`, `UnexpectedEnd`, `DivisionByZero`, `Overflow`, `UnknownFunction`,
  `WrongArity`, `DomainError`, `UndefinedVariable`, `ConstantReassignment`,
  `FunctionAlreadyDefined`, `CannotRedefineBuiltin`
- Plot errors (new in v0.5.0):
  - `UndefinedFunction(name)` → `"undefined function: {name}"` (distinct from `UnknownFunction`)
  - `OutputWriteError(reason)` → `"cannot write output: {reason}"`
  - `UnsupportedFormat(ext)` → `"unsupported format: {ext}; use .png or .svg"`
  - `DomainEmpty` → `"expression undefined over entire domain"`
  - `InvalidDomainBounds` → `"xmin must be less than xmax"`

**Files:** `src/calc/errors.py`

**Dependencies:** none

---

### Module: png

**Responsibility:** Encode an 8-bit RGB pixel buffer as a valid PNG file using only
`struct` and `zlib` from the Python standard library.

**Key interfaces:**
- `encode_png(width: int, height: int, pixels: list[tuple[int, int, int]]) → bytes`
  — `pixels` is a row-major list of `(r, g, b)` tuples; returns a complete PNG file
  as bytes
- `DEFAULT_WIDTH: int = 800`
- `DEFAULT_HEIGHT: int = 600`

**Files:** `src/calc/png.py`

**Dependencies:** `struct`, `zlib` (stdlib only)

---

### Module: plotter

**Responsibility:** Sample an expression AST over a domain, detect discontinuities,
compute y-range and tick marks, and produce a device-independent `Scene` dataclass;
own all curve-generation and axis mathematics; have no import of any renderer.

**Key interfaces:**
- `Scene` frozen dataclass: `width`, `height`, `x_min`, `x_max`, `y_min`, `y_max`,
  `x_ticks: tuple[tuple[float, str], ...]`, `y_ticks: tuple[tuple[float, str], ...]`,
  `segments: tuple[tuple[tuple[float, float], ...], ...]`
- `build_scene(ast: ASTNode, x_min: float, x_max: float, width: int, height: int) → Scene`
- Internal: `sample_expression(ast, x_values) → list[tuple[float, float | None]]`
- Internal: `build_segments(raw) → list[list[tuple[float, float]]]`
- Internal: `calc_ticks(data_min, data_max, target_n=6) → list[tuple[float, str]]`

**Files:** `src/calc/plotter.py`

**Dependencies:** `evaluator` (`evaluate`, `_CONSTANTS_VALUES`), `errors`
(`CalcError`, `DomainEmpty`), `statistics`, `math`

---

### Module: renderer

**Responsibility:** Consume a `Scene` and write an image file; dispatch to the correct
concrete renderer based on file extension; define the `Renderer` protocol that future
renderers (v0.7.x Tk) must satisfy.

**Key interfaces:**
- `Renderer` Protocol: `render(scene: Scene, output: Path) → None`
  — raises `OSError` on write failure
- `get_renderer(output: Path) → Renderer` — dispatches by `output.suffix`
- `PngRenderer` — implements `Renderer`; uses `encode_png` from `calc.png`
- `SvgRenderer` — implements `Renderer`; generates XML via `xml.etree.ElementTree`

**Files:**
- `src/calc/renderer/__init__.py` — `Renderer` Protocol, `get_renderer`
- `src/calc/renderer/png.py` — `PngRenderer`
- `src/calc/renderer/svg.py` — `SvgRenderer`

**Dependencies:** `plotter` (`Scene`), `png` (`encode_png`), `xml.etree.ElementTree`,
`pathlib`

---

### Module: cli

**Responsibility:** Parse CLI arguments, route to the legacy expression pipeline or
the plot subcommand, thread both `env` and `fn_env` through the statement loop for the
legacy path, and set stdout/stderr/exit-code according to the result.

**Key interfaces:**
- `main()` — entry point called from `__main__.py`
- `SUBCOMMANDS: frozenset[str] = frozenset({"plot"})` — routing sentinel
- `_legacy_eval()` — existing `calc '<expr>'` path; unchanged from v0.4.x
- `_build_parser() → argparse.ArgumentParser` — defines `plot` subparser with
  `expression`, `--xmin`, `--xmax`, `--width`, `--height`, `--output`
- `run_plot(args: argparse.Namespace) → None` — validates args, calls `build_scene`,
  dispatches to renderer; translates `CalcError`/`OSError` to stderr + exit 1

**Files:** `src/calc/__main__.py`

**Dependencies:** `lexer`, `parser`, `evaluator`, `errors`, `plotter`, `renderer`,
`argparse`, `sys`, `pathlib`

---

## Cross-Cutting Concerns

### Error handling strategy

All errors descend from `CalcError`. The CLI catches `CalcError`, writes
`"error: " + e.description()` to stderr, and exits 1. No error type is swallowed
silently. `OSError` from the renderer is caught and re-raised as `OutputWriteError`
before the top-level handler sees it.

**Error classes added in v0.5.0:**

| Class | Raised by | `description()` output |
|---|---|---|
| `UndefinedFunction(name)` | `run_plot` (re-wraps evaluator `UnknownFunction`) | `undefined function: <name>` |
| `OutputWriteError(reason)` | `run_plot` (wraps `OSError`) | `cannot write output: <reason>` |
| `UnsupportedFormat(ext)` | `run_plot` (CLI validation) | `unsupported format: <ext>; use .png or .svg` |
| `DomainEmpty` | `plotter.build_scene` (post-sampling) | `expression undefined over entire domain` |
| `InvalidDomainBounds` | `run_plot` (CLI validation) | `xmin must be less than xmax` |

**Note on `UnknownFunction` vs `UndefinedFunction`:** `UnknownFunction` (v0.1.x)
produces `"unknown function '<name>'"` and is retained unchanged to avoid breaking
existing tests. `UndefinedFunction` (v0.5.0) produces the spec-mandated
`"undefined function: <name>"` format and is used exclusively on the plot path. A
follow-up issue should decide whether to consolidate the two classes.

**Plot-specific error flow:**
- `--xmin ≥ --xmax` → `InvalidDomainBounds`, exit 1
- unknown `--output` extension → `UnsupportedFormat`, exit 1
- expression parse error → `UnexpectedToken`/`UnexpectedEnd`, exit 1
- expression contains undefined function → `UndefinedFunction`, exit 1
- expression contains undefined variable (not `x`) → `UndefinedVariable`, exit 1
- all domain samples fail → `DomainEmpty`, exit 1
- output path not writable → `OutputWriteError`, exit 1
- no expression argument → argparse prints usage to stderr, exit 1

All v0.1.x–v0.4.x error classes (`DivisionByZero`, `DomainError`, `Overflow`,
`UndefinedVariable`, `ConstantReassignment`, `FunctionAlreadyDefined`,
`CannotRedefineBuiltin`) are propagated unchanged on the legacy path.

### Testing approach

Tests are organised as one file per layer, following the established convention.
No new top-level test files are created for the expression pipeline. Plot-specific
tests live in `tests/test_plot.py` (new file; justified because the plot command
is a distinct subsystem with its own test patterns).

**Three-tier strategy for image correctness (research #171):**

1. **Scene IR inspection** (primary): call `build_scene(...)` directly and assert
   mathematical invariants on `scene.segments`, `scene.x_ticks`, `scene.y_ticks`,
   and axis bounds. Display-free, cross-platform identical, fast.

2. **PNG pixel sampling** (renderer verification): decompress the IDAT chunk using
   `zlib.decompress` (stdlib); index scanlines at fixed byte offsets; check a ±2 px
   neighbourhood at the world origin to verify the renderer places the curve
   correctly. Tolerates sub-pixel rounding without making the test meaninglessly
   loose. Pixel coordinates are derived from the `Scene` IR (not hard-coded) to
   survive padding changes.

3. **SVG structural assertions** via `xml.etree.ElementTree` (stdlib): assert at
   least one `<polyline>` or `<path>` element exists; assert minimum point count
   (≥ `width` samples); assert y-pixel range spans a meaningful fraction of image
   height.

**No golden-file / snapshot tests.** PNG bytes differ between macOS and Linux due to
`zlib` compression defaults; snapshot maintenance requires human review; the
cross-platform CI requirement makes snapshot tests too fragile.

**Test file plan:**

| File | New/Extended | Coverage |
|---|---|---|
| `tests/test_lexer.py` | Existing | No new cases (no new tokens in v0.5.0) |
| `tests/test_parser.py` | Existing | No new cases (no new syntax in v0.5.0) |
| `tests/test_evaluator.py` | Existing | No new cases (no evaluator changes in v0.5.0) |
| `tests/test_errors.py` | Extended | New `UndefinedFunction`, `OutputWriteError`, `UnsupportedFormat`, `DomainEmpty`, `InvalidDomainBounds` |
| `tests/test_png.py` | New | `encode_png` unit tests: signature, dimensions, pixel values |
| `tests/test_plotter.py` | New | `build_scene` unit tests: Scene IR assertions, discontinuity detection, tick bounds, DomainEmpty |
| `tests/test_renderer.py` | New | PNG/SVG dimension assertions, SVG structural assertions, `get_renderer` dispatch |
| `tests/test_plot.py` | New | CLI integration: exit codes, stderr messages, PNG pixel sampling, end-to-end success criteria |
| `tests/test_cli.py` | Existing | Legacy path unchanged; add subcommand routing smoke test |

**Existing tests:** all v0.1.x–v0.4.x success criteria must continue to pass. The
only changes to existing test files are the five new error-class assertions in
`tests/test_errors.py`.

### Configuration and environment

- No configuration files. All behaviour is determined by CLI arguments.
- `_DEFAULT_ENV` and `_CONSTANTS_VALUES` are module-level constants in
  `evaluator.py` — the single source of truth for built-in constant values.
- Fresh `dict(_DEFAULT_ENV)` and `{}` are created per invocation for `env` and
  `fn_env` respectively — no mutable global state.
- `_CONSTANTS_VALUES` is passed to `build_scene` so that named constants (`pi`, `e`)
  are available in plotted expressions.
- Plot defaults (`DEFAULT_WIDTH = 800`, `DEFAULT_HEIGHT = 600`) live in `png.py` and
  are referenced by both the CLI and tests.

### Observability / logging

No logging in v0.5.0. All user-visible output is either the numeric result on stdout
(legacy path), nothing on stdout (plot path on success), or a single
`"error: ..."` line on stderr (any failure), matching the established contract.
The `plot` subcommand writes nothing to stdout on success.

---

## Open Questions

The following decisions are deferred to the LLD for each module:

1. **`plotter` LLD** — Exact `linspace` implementation (use `[x_min + i*(x_max-x_min)/(n-1) for i in range(n)]` vs `statistics`/`math` helpers vs importing `range` with float step); whether `build_scene` returns `Scene` with tuple-of-tuples segments or converts a working `list[list[tuple]]` at the end; exact handling of the `y_min == y_max` (constant-function) case in the padding step.

2. **`renderer` LLD** — Exact coordinate transform used by `PngRenderer` for world→pixel mapping (top-left vs bottom-left origin; rounding mode for sub-pixel coordinates); whether axis lines at x=0 and y=0 are drawn only when within the domain/range; line thickness (1 px vs 2 px) for curve vs axis; SVG viewBox vs fixed width/height attributes; tick label font size and placement for the PNG renderer (hardcoded pixel font vs no labels in v0.5.0).

3. **`png` LLD** — Whether `encode_png` uses a single `IDAT` chunk or multiple; exact `zlib.compress` level used (level=6 recommended in research); whether width/height guard uses `assert` or raises a custom error.

4. **`errors` LLD** — Whether `UndefinedFunction` is a sibling of `UnknownFunction` or a subclass; exact `super().__init__` call signature for the new error classes.

5. **`cli` LLD** — Whether `run_plot` lives in `__main__.py` or in a separate `src/calc/plot.py`; exact guard for the "no expression argument" path (argparse `required` vs manual check); whether `get_renderer` is called in `cli` or in `run_plot`; whether the deferred import `from calc.plotter import build_scene` at the top of `run_plot` is used or a module-level import is preferred.
