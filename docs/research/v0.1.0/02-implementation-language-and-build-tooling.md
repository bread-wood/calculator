# Research: Implementation Language and Build Tooling
**Issue:** #2
**Milestone:** v0.1.0
**Date:** 2026-03-04
**Status:** Decided

---

## Decision

**Use C with a POSIX Makefile.**

---

## Rationale

The spec has one hard constraint that eliminates most candidates:

> Runs on macOS and Linux with no external runtime dependencies beyond the standard library

Every platform in scope ships a C compiler (`cc` resolves to clang on macOS, gcc on Linux) and `make`. No toolchain install is required at all — not even a package manager invocation.

### Candidate evaluation

| Criterion | C | Go | Python | Rust | Shell |
|-----------|---|----|--------|------|-------|
| Zero runtime deps | ✅ libc only | ✅ static binary | ❌ needs Python 3 | ✅ static binary | ⚠️ needs `bc` for floats |
| Toolchain pre-installed | ✅ cc + make on every POSIX target | ❌ must install Go | ✅/❌ Python may be absent | ❌ must install Rust | ✅ |
| `make test` integration | ✅ native | ⚠️ Makefile wrapper | ⚠️ Makefile wrapper | ⚠️ Makefile wrapper | ✅ native |
| Floating-point output formatting | ✅ `printf`/`%g` handles integer-vs-decimal | ✅ `strconv.FormatFloat` | ✅ | ✅ | ❌ limited |
| Single binary named `calc` | ✅ trivial | ✅ | ❌ unless PyInstaller | ✅ | ✅ (script) |
| Future extensibility (functions, vars) | ✅ | ✅ | ✅ | ✅ | ❌ hard |
| Overflow detection | ✅ `double` IEEE 754 inf | ✅ | ✅ | ✅ | ❌ |

**Go** and **Rust** are technically sound but require a separately installed toolchain on every build machine. That adds a hidden dependency for CI and any contributor bootstrapping the project. Both also produce larger binaries (~2 MB+) for a ~200-line program.

**Python** requires Python 3 to be present at runtime on the end-user's machine — it cannot satisfy the zero-runtime-dep constraint without a bundler, and bundlers (PyInstaller, shiv) add significant complexity.

**Shell** cannot natively handle floating-point arithmetic (`calc '10 / 4'` → `2.5`) without calling `bc` or `awk`, both of which are external dependencies that may not be present.

**C** satisfies every constraint directly:
- `cc -o calc calc.c -lm` produces a statically-linked-against-libc binary with no additional runtime.
- `double` (IEEE 754 64-bit) covers the required numeric range; `printf("%.10g", result)` yields `2` for `2.0` and `2.5` for `2.5` with no extra logic.
- A single `Makefile` with `test:` target runs a shell test harness — no wrapper layer needed.
- The recursive-descent parser architecture (see issue #3 research) extends cleanly to functions and variables in future versions.

### Memory management scope

For a single-pass CLI that exits immediately after printing one line, memory management complexity is near zero: no heap allocation is required. The entire program fits in stack-allocated structs and string literals.

---

## Build Toolchain Specification

### Compiler

```
cc -std=c11 -Wall -Wextra -Werror -o calc calc.c -lm
```

- `cc` — resolves to the platform default (clang on macOS, gcc on Linux)
- `-std=c11` — modern C, available on both platforms since 2012
- `-lm` — math library (needed if `sin`/`sqrt` are added in future; costs nothing now)

### Makefile targets

```makefile
.PHONY: all build test clean

all: build

build:
	cc -std=c11 -Wall -Wextra -Werror -o calc calc.c -lm

test: build
	@bash tests/run_tests.sh

clean:
	rm -f calc
```

`make test` chains through `build` first, satisfying the spec requirement that a clean checkout runs tests with a single command.

### Test harness

A POSIX shell script (`tests/run_tests.sh`) drives all acceptance criteria:

```sh
#!/bin/sh
pass=0; fail=0
check() {
    actual=$(eval "$1" 2>&1); expected="$2"
    if [ "$actual" = "$expected" ]; then pass=$((pass+1))
    else fail=$((fail+1)); echo "FAIL: $1 => '$actual' (expected '$expected')"
    fi
}
check "./calc '2 + 3'"            "5"
check "./calc '10 / 4'"           "2.5"
check "./calc '2 + 3 * 4'"        "14"
check "./calc '(2 + 3) * 4'"      "20"
check "./calc '4 / 2'"            "2"
# ... (error cases check stderr + exit code)
echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
```

This is POSIX `/bin/sh` with no external dependencies.

---

## Installation / Bootstrap

### macOS
```sh
xcode-select --install   # installs cc + make (one-time)
make build               # produces ./calc
```

### Linux (Debian/Ubuntu)
```sh
apt-get install -y build-essential   # installs cc + make (one-time)
make build
```

### Linux (Alpine / minimal)
```sh
apk add build-base
make build
```

All CI environments (GitHub Actions `ubuntu-latest`, `macos-latest`) have `cc` and `make` pre-installed; no setup step is needed beyond checkout.

---

## Acceptance Criteria Status

- [x] Language has a path to a zero-external-runtime-dep executable — C compiles to a native binary linked only against libc
- [x] `make test` integration is straightforward — native Makefile, no wrapper
- [x] Installation/build instructions are simple for macOS and Linux — `cc` and `make` are pre-installed or a single package away
- [x] Decision documented with rationale — this document

---

## Rejected Alternatives

**Go** — requires `go` toolchain; not pre-installed on standard macOS or most CI images without explicit setup. Would otherwise be a strong second choice.

**Rust** — requires `rustup` + `cargo`; heavier toolchain than the project warrants for a ~200-line program.

**Python** — runtime dependency on the end-user machine; cannot satisfy zero-dep constraint without a bundler.

**Shell** — cannot natively compute `10 / 4 = 2.5` without `bc`; fragile for future extension to functions and variables.
