# Research: Subcommand Dispatch — Routing `calc plot` Alongside `calc <expr>`

**Issue:** #168
**Milestone:** v0.5.0
**Date:** 2026-03-05

---

## Summary

**Recommendation: argparse subparsers with a legacy-expression fallback via early `sys.argv` inspection.**

Use `argparse.add_subparsers()` for `plot` (and future subcommands). Preserve the existing `calc '<expr>'` behavior unchanged by detecting the legacy invocation before argparse runs: if `sys.argv[1]` is not a known subcommand keyword, treat the entire invocation as the old expression path.

---

## Options Considered

### 1. Manual `sys.argv` routing

```python
if len(sys.argv) >= 2 and sys.argv[1] == 'plot':
    # plot path
else:
    # legacy expression path
```

**Pros:** Zero boilerplate, no new imports, completely obvious.
**Cons:** `--help` for `plot` must be written by hand; `--xmin`, `--xmax`, `--width`, `--height`, `--output` type conversion and validation must be written by hand; grows awkward when v0.6.x adds more flags or v0.7.x adds another subcommand.

**Verdict: rejected.** The flag surface for `plot` is non-trivial (five flags, two types). Manual parsing duplicates what `argparse` already does reliably.

---

### 2. `argparse` subparsers (standard library)

```python
parser = argparse.ArgumentParser(...)
subparsers = parser.add_subparsers(dest='subcommand')
plot_parser = subparsers.add_parser('plot', ...)
plot_parser.add_argument('expression')
plot_parser.add_argument('--xmin', type=float, default=-10)
# ...
```

`argparse` handles `--help`, type coercion, and error messages for free. The only challenge is the legacy invocation `calc '<expr>'` (no subcommand). `argparse` without a default subcommand treats this as an error.

**Solution:** Early-exit branch before `argparse` runs:

```python
SUBCOMMANDS = frozenset({'plot'})

def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SUBCOMMANDS:
        _legacy_eval()   # existing expression path, unchanged
        return
    # argparse dispatch for subcommands
    ...
```

This keeps the legacy path completely unchanged and isolates `argparse` to subcommand branches only.

**Pros:** Type-safe flag parsing; `--help` generated automatically; clean extension point for v0.6.x/v0.7.x subcommands (just add to `SUBCOMMANDS` and `add_subparsers`).
**Cons:** Two parallel entry points (`_legacy_eval` + argparse subcommand); slightly more boilerplate than manual routing.

**Verdict: recommended.**

---

### 3. Third-party CLI libraries (Click, Typer)

Ruled out: `pyproject.toml` has `dependencies = []` and the spec requires no external runtime dependencies.

---

## Chosen Strategy: `argparse` subparsers + early-exit legacy branch

### Rationale

- Five named flags for `plot` make manual parsing error-prone and verbose.
- `argparse` is stdlib; no dependency cost.
- The early-exit pattern keeps backwards compatibility without any argparse hacks.
- v0.6.x (multiple curves) and v0.7.x (GUI) only require adding a new `add_subparsers` entry and extending `SUBCOMMANDS`; `_legacy_eval` is never touched.

### Does legacy `calc '<expr>'` stay as-is or migrate to `calc eval '<expr>'`?

**Stays as-is.** The spec's success criteria make no mention of a `calc eval` alias, and explicitly lists `calc plot 'sin(x)'` as the new invocation. Backwards compatibility is preserved by the early-exit check: any first argument that is not a known subcommand keyword is treated as an expression.

---

## Resulting `__main__.py` Top-Level Structure (pseudocode)

```python
import argparse
import sys
from calc.errors import CalcError, error_message
# ... other calc imports ...

SUBCOMMANDS = frozenset({"plot"})


def _legacy_eval() -> None:
    """Existing calc '<expr>' path — unchanged from v0.4.x."""
    if len(sys.argv) == 1:
        print("usage: calc '<expression>'", file=sys.stderr)
        sys.exit(1)
    if len(sys.argv) != 2:
        print(error_message(ExpectedSingleArg()), file=sys.stderr)
        sys.exit(1)
    expression = sys.argv[1]
    if expression == "":
        print(error_message(EmptyExpression()), file=sys.stderr)
        sys.exit(1)
    try:
        # lexer → parser → evaluator pipeline (unchanged)
        ...
    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)
    print(format_result(last_result))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calc")
    subs = parser.add_subparsers(dest="subcommand")

    plot = subs.add_parser("plot", help="plot an expression to an image file")
    plot.add_argument("expression", help="expression in x to plot")
    plot.add_argument("--xmin",   type=float, default=-10)
    plot.add_argument("--xmax",   type=float, default=10)
    plot.add_argument("--width",  type=int,   default=800)
    plot.add_argument("--height", type=int,   default=600)
    plot.add_argument("--output", default="./plot.png")

    return parser


def main() -> None:
    # Early-exit: if no subcommand keyword is present, run legacy eval path.
    if len(sys.argv) < 2 or sys.argv[1] not in SUBCOMMANDS:
        _legacy_eval()
        return

    parser = _build_parser()
    args = parser.parse_args()

    if args.subcommand == "plot":
        from calc.plot import run_plot   # import deferred to keep startup fast
        run_plot(args)


if __name__ == "__main__":
    main()
```

### Key properties of this structure

| Property | Outcome |
|---|---|
| `calc 'sin(x) + 1'` | Hits `_legacy_eval`; zero change in behavior |
| `calc plot 'sin(x)'` | Dispatched via argparse; flags parsed and type-coerced |
| `calc plot --help` | argparse-generated help for `plot` |
| `calc --help` | argparse-generated top-level help listing `plot` |
| Adding v0.6.x `curves` subcommand | Add `"curves"` to `SUBCOMMANDS`; add `subs.add_parser("curves", ...)` |
| Flag parsing for `--xmin` etc. | `argparse` handles type, default, and error messages |

---

## Follow-up Issues

None spawned from this research. Implementation of `__main__.py` restructuring is part of the v0.5.0 implementation issue.
