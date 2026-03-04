# Project Layout, Makefile Targets, and Installation Conventions
**Issue:** #7 | **Milestone:** v0.1.0 | **Date:** 2026-03-04

---

## Recommendation Summary

Use a flat-then-package Python layout with a `src/calc/` package, a single `Makefile`
wrapping `uv` commands, and a `bin/calc` entry-point script. This satisfies `make test`
on both macOS and Linux, keeps CI simple, and accommodates future source additions
without Makefile surgery.

---

## 1. Constraints and Prior Decisions

| Constraint | Source |
|---|---|
| `make test` must pass clean on macOS and Linux | Spec success criteria |
| Binary invokable as `calc` | Spec interface contract |
| No external runtime dependencies beyond stdlib | Spec constraints |
| CI uses `uv run pytest` + `uv run ruff check` | `.github/workflows/ci.yml` |
| Implementation language: Python | `testing-strategy.md` (issue #5) + CI workflow |
| Recursive-descent parser with AST | `parser-architecture.md` (issue #1) |

---

## 2. Recommended Directory Layout

```
calculator/
├── Makefile
├── pyproject.toml          # project metadata + dependencies
├── src/
│   └── calc/
│       ├── __init__.py
│       ├── __main__.py     # entry point: python -m calc '<expr>'
│       ├── lexer.py
│       ├── parser.py
│       └── evaluator.py
├── tests/
│   ├── test_lexer.py
│   ├── test_parser.py
│   ├── test_evaluator.py
│   └── test_cli.py         # subprocess-based end-to-end tests
├── bin/
│   └── calc                # thin shell wrapper (see §4)
└── .github/
    └── workflows/
        └── ci.yml
```

### Rationale for each choice

**`src/` layout** — Placing the package under `src/calc/` rather than a top-level `calc/`
prevents accidental import of the source tree before installation and is the modern Python
project convention recommended by PyPA. It requires zero extra tooling — `uv` handles the
`src` layout automatically when `pyproject.toml` declares `packages = [{include = "calc",
from = "src"}]`.

**`src/calc/__main__.py`** — Makes `python -m calc '<expr>'` work without needing the
`bin/calc` wrapper during development. The `bin/calc` script uses this same entry point.

**Module decomposition matches parser architecture** — `lexer.py`, `parser.py`,
`evaluator.py` map directly to the three processing layers described in the parser
architecture research. Each module can grow independently; adding named functions
(v0.2.0) means editing `lexer.py` and `evaluator.py` only. No Makefile changes needed.

**`tests/` at project root** — pytest discovers `tests/` automatically. Adding new test
files requires no Makefile or `pyproject.toml` changes.

---

## 3. Makefile Targets

```makefile
.PHONY: all build test lint clean install

# Default: build the entry-point script and verify it runs
all: build

build:
	uv sync --frozen
	chmod +x bin/calc
	@echo "Build complete. Run: ./bin/calc '2 + 3'"

test: build
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/

clean:
	rm -rf .venv __pycache__ src/calc/__pycache__ tests/__pycache__ \
	       .pytest_cache dist *.egg-info

install: build
	install -m 755 bin/calc /usr/local/bin/calc
	@echo "Installed to /usr/local/bin/calc"
```

### Key design decisions

**`test` depends on `build`** — A clean checkout runs `make test` as a single command.
`uv sync --frozen` ensures a reproducible environment using the locked `uv.lock` file.

**No compiler or language toolchain install step in CI** — `ubuntu-latest` and
`macos-latest` runners both have Python 3 and `uv` available (or `uv` is installed via
`astral-sh/setup-uv@v4` as the CI already does). No additional setup is needed.

**`lint` is separate from `test`** — CI can run them as distinct steps with distinct
failure messages. Local developers can run `make test` without linting.

**`install` is optional** — Not required for `make test` or CI. Documents the manual
path for adding `calc` to `PATH` system-wide.

---

## 4. Binary Invocation: `bin/calc`

```sh
#!/bin/sh
# bin/calc — thin wrapper; invokes the calc package via uv
exec "$(dirname "$0")/../.venv/bin/python" -m calc "$@"
```

Or, after `uv sync`, a generated console-script entry point can be used instead:

```toml
# pyproject.toml
[project.scripts]
calc = "calc.__main__:main"
```

With this declaration, `uv sync` creates `.venv/bin/calc` automatically. The `bin/calc`
shell wrapper then becomes:

```sh
#!/bin/sh
exec "$(dirname "$0")/../.venv/bin/calc" "$@"
```

**Trade-off table:**

| Approach | Pros | Cons |
|---|---|---|
| `python -m calc` wrapper | Works with any Python ≥ 3.8 | Requires `.venv` path knowledge |
| `pyproject.toml` console script | uv generates it; idiomatic | `.venv/bin/calc` is `.venv`-relative |
| Compiled binary (shiv/PyInstaller) | Truly standalone | Adds build complexity; violates zero-dep spirit |

**Recommendation:** use the `[project.scripts]` entry point. `uv sync` creates
`.venv/bin/calc`; `bin/calc` wraps it with a portable `#!/bin/sh` shim. CI and tests
reference `./bin/calc` as the canonical binary path.

---

## 5. CI Configuration

The existing `ci.yml` runs on `ubuntu-latest` only. To satisfy the macOS/Linux matrix
requirement from the spec:

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Run tests
        run: make test
      - name: Lint
        run: make lint
```

Using `make test` in CI rather than `uv run pytest` directly:
- Validates the Makefile itself (catches broken targets early)
- Mirrors what contributors run locally
- No additional setup: `uv sync` inside `make build` handles the venv

---

## 6. Adding Future Source Files — Zero Makefile Surgery

When v0.2.0 adds named functions or variables:

1. Add `src/calc/functions.py` or `src/calc/variables.py` — no Makefile change.
2. Add `tests/test_functions.py` — pytest discovers it automatically.
3. If a new operator requires a new precedence level: add a method to `parser.py` only.

The only time `Makefile` changes are needed is if a new high-level target category is
added (e.g., `make docs`, `make bench`).

---

## 7. Acceptance Criteria

- [x] `make test` is a single command that runs all tests on both platforms
  — `make test` → `uv sync` → `uv run pytest tests/`; works on macOS and Linux wherever
  `uv` is available (CI installs it via `astral-sh/setup-uv@v4`)
- [x] Repository layout is documented — §2 above
- [x] Binary build and invocation path are clear
  — `make build` → `.venv/bin/calc` created by uv; `bin/calc` wrapper at repo root
- [x] Layout accommodates future source file additions without Makefile surgery
  — new `.py` files under `src/calc/` and `tests/` require no Makefile edits

---

## 8. Rejected Alternatives

**Flat layout (`calc/` at repo root)** — Causes import ambiguity if the package name
matches a stdlib module; also the old convention. `src/` layout is preferred for new
projects.

**Single-file `calc.py`** — Works for v0.1.0 but forces a disruptive restructuring when
lexer/parser/evaluator need to be split. Starting with the package layout costs nothing
and avoids the future churn.

**`Makefile` with `python` instead of `uv run`** — Breaks if the system Python differs
from the project's pinned version. `uv run` always uses the project-local venv.

**Separate `Makefile` per subdirectory** — Adds indirection for no gain at this project
scale. A single root `Makefile` with `tests/` as a target path is simpler.
