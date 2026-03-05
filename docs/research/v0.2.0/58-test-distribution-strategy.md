# Research: Test Distribution Strategy for Function and Constant Coverage

**Issue:** #58
**Milestone:** v0.2.0
**Date:** 2026-03-04
**Branch:** 58-research-test-distribution-strategy-for

---

## Summary

New tests for v0.2.0 should be distributed across all five existing test files following established patterns. Unit tests cover components in isolation for fast feedback; CLI integration tests cover every spec success criterion exactly as stated. No spec criterion should be tested only at CLI level if it involves new evaluator logic—but CLI tests are still required for each observable output criterion. The 27 spec items split cleanly across the four layers below.

---

## Guiding Principles

1. **Each component is unit-tested at its own layer.** Lexer tests verify tokens; parser tests verify AST shape; evaluator tests verify numeric results and error raises; error tests verify message strings.
2. **CLI tests cover every spec success criterion.** The spec criteria are defined at the CLI boundary (`calc '<expr>'` → stdout/stderr/exit). Each criterion gets exactly one `test_cli.py` case.
3. **No duplication of logic.** CLI tests assert observable output only; they do not re-test internal dispatch paths. Unit tests assert internal contracts that CLI tests cannot isolate.
4. **Error message tests belong in `test_errors.py`.** The parametrize table in `test_errors.py` is the authority for the `error_message(e)` contract; new error classes go there first.

---

## Layer-by-Layer Plan

### 1. `test_lexer.py` — IDENT token cases

v0.2.0 adds a new `TokenType.IDENT` for function names and constants. The lexer must be tested at this layer because the parser cannot distinguish a tokenization error from a parse error.

**Add a parametrized `test_ident_tokens` group:**

| Input | Expected token(s) |
|---|---|
| `"sqrt"` | `IDENT("sqrt")` |
| `"pi"` | `IDENT("pi")` |
| `"atan2"` | `IDENT("atan2")` |
| `"abc123"` | `IDENT("abc123")` — multi-char alphanumeric |
| `"x"` | `IDENT("x")` — single-char identifier |

**Add edge-case tests:**

| Input | Key assertion |
|---|---|
| `"sqrt(9)"` | token sequence: `IDENT("sqrt"), LPAREN, NUMBER("9"), RPAREN, EOF` |
| `"1e10"` | token sequence: `NUMBER("1e10"), EOF` — the `e` inside a numeric literal is **not** tokenized as `IDENT` |
| `"1 e"` | token sequence: `NUMBER("1"), IDENT("e"), EOF` — spacing separates the constant `e` from the number |
| `"2*pi"` | token sequence: `NUMBER("2"), STAR, IDENT("pi"), EOF` |

The `1e10` case is the critical edge case: lexers that scan identifiers before numbers (or use a naive "starts with alpha" rule without lookahead) will mislabel the `e` in scientific notation. This must be verified explicitly at the lexer layer.

**Total new lexer test cases:** ~9 (6 parametrized IDENT cases + 3 edge cases)

---

### 2. `test_parser.py` — Call and Name AST nodes

v0.2.0 adds `Call(name, args)` and `Name(name)` AST node types. Parser tests verify that the grammar produces the correct tree shape regardless of whether evaluation would succeed.

**Add cases for `Name` nodes (constants):**

```python
parse("pi")   == Name("pi")
parse("e")    == Name("e")
parse("2*pi") == BinaryOp("*", Number(2.0), Name("pi"))
```

**Add cases for `Call` nodes (function calls):**

```python
parse("sqrt(9)")       == Call("sqrt", [Number(9.0)])
parse("pow(2, 10)")    == Call("pow", [Number(2.0), Number(10.0)])
parse("abs(-5)")       == Call("abs", [UnaryOp("-", Number(5.0))])
parse("sqrt()")        == Call("sqrt", [])          # zero args — parse succeeds, arity checked at eval
```

**Add a nested-call case:**

```python
parse("sqrt(pow(3,2)+pow(4,2))") == Call("sqrt", [
    BinaryOp("+",
        Call("pow", [Number(3.0), Number(2.0)]),
        Call("pow", [Number(4.0), Number(2.0)])
    )
])
```

This is the exact composition example from the spec. It verifies that nested function calls round-trip through the parser correctly before any evaluator logic is involved.

**Arity at parse time:** Arity validation belongs in the evaluator (the function registry knows expected counts), not the parser. The parser should accept any call with any number of arguments and build the `Call` node faithfully. `Call("sqrt", [])` and `Call("pow", [Number(2.0)])` should parse without error—the evaluator raises `WrongArgCount`. No parse-time arity tests are needed; the parser test for `sqrt()` above confirms zero-arg parse succeeds.

**Total new parser test cases:** ~8 (3 Name, 4 Call, 1 nested)

---

### 3. `test_evaluator.py` — Function and constant dispatch paths

All 14 new dispatch paths (10 single-arg functions, 2 two-arg functions, 2 constants) should be covered at the unit level. Unit tests here are fast (in-process), give precise failure messages, and isolate evaluator logic from subprocess overhead.

**Add a parametrized `test_evaluate_functions` group:**

| Expression | Expected |
|---|---|
| `"sqrt(9)"` | `3.0` |
| `"sqrt(2)"` | `1.4142135623730951` |
| `"abs(-5)"` | `5.0` |
| `"floor(2.7)"` | `2.0` |
| `"ceil(2.3)"` | `3.0` |
| `"round(2.5)"` | `3.0` |
| `"sin(0)"` | `0.0` |
| `"cos(0)"` | `1.0` |
| `"log(1)"` | `0.0` |
| `"exp(0)"` | `1.0` |
| `"pow(2, 10)"` | `1024.0` |
| `"atan2(1, 1)"` | `0.7853981633974483` |
| `"pi"` | `3.141592653589793` |
| `"e"` | `2.718281828459045` |

**Add composition tests:**

```python
eval_expr("2 * pi")                        == 6.283185307179586
eval_expr("sqrt(pow(3,2)+pow(4,2))")       == 5.0
```

**Add error-raise tests:**

| Expression | Expected exception |
|---|---|
| `"sqrt(-1)"` | `DomainError` |
| `"log(0)"` | `DomainError` |
| `"unknown(5)"` | `UnknownFunction` |
| `"sqrt()"` | `WrongArgCount` |
| `"pow(2)"` | `WrongArgCount` |

Domain error tests **must** be at the evaluator unit level. `DomainError` is the analogue of `DivisionByZero`—it is raised inside the evaluator, and the unit test pinpoints the raise site. `UnknownFunction` and `WrongArgCount` likewise originate in the evaluator's function registry dispatch; unit tests isolate them cleanly.

Verify error fields for `UnknownFunction` and `WrongArgCount`:

```python
with pytest.raises(UnknownFunction) as exc_info:
    eval_expr("unknown(5)")
assert exc_info.value.name == "unknown"

with pytest.raises(WrongArgCount) as exc_info:
    eval_expr("sqrt()")
assert exc_info.value.name == "sqrt"
assert exc_info.value.expected == 1
```

**Total new evaluator test cases:** ~21 (14 dispatch + 2 composition + 5 error-raise + field assertions)

---

### 4. `test_errors.py` — Error message strings

The parametrize table in `test_errors.py` is the canonical test for the `error_message(e) -> str` contract. All three new error classes belong here.

**Add to the `test_error_message` parametrize table:**

| Instance | Expected string |
|---|---|
| `DomainError()` | `"error: domain error"` |
| `UnknownFunction("unknown")` | `"error: unknown function: unknown"` |
| `UnknownFunction("foo")` | `"error: unknown function: foo"` |
| `WrongArgCount("sqrt", 1)` | `"error: wrong number of arguments: sqrt expects 1"` |
| `WrongArgCount("pow", 2)` | `"error: wrong number of arguments: pow expects 2"` |

Two `UnknownFunction` cases are warranted because the message embeds the runtime name; one case for a short single-token name and one for a longer name confirms string interpolation is correct.

**Add to `test_all_subclasses_inherit_from_calc_error`:**

```python
DomainError, UnknownFunction, WrongArgCount
```

**Update `test_error_message_unknown_subclass`:** The existing test verifies that `error_message(BogusError())` raises `TypeError`. This test is unaffected if Option B from research #55 (`description()` method) is adopted. No change needed.

**Total new error test cases:** ~7 (5 message cases + 3 subclass inheritance additions)

---

### 5. `test_cli.py` — Spec success criteria (integration layer)

Each of the 21 explicit spec checklist items (16 success cases + 5 error cases) maps to one `test_cli.py` case. The `make test` criterion (#22) is satisfied when all tests pass and requires no additional test case.

**Rationale for full CLI coverage (not sampling):**

- The spec acceptance criteria are defined at the CLI boundary. A passing evaluator unit test for `sqrt(9)` does not guarantee that the CLI routes the result correctly through `format_result` to stdout with exit 0.
- `test_cli.py` already has 1:1 coverage of all v0.1.x spec items (`test_addition`, `test_division_fractional`, etc.). Consistency demands the same for v0.2.0.
- The overhead is low: each CLI test is ~4 lines and subprocess tests catch integration failures (argument parsing, exit codes) invisible to unit tests.

**Recommended test names and assertions:**

| Test name | Input | stdout | stderr | exit |
|---|---|---|---|---|
| `test_sqrt_integer` | `sqrt(9)` | `3` | `""` | 0 |
| `test_sqrt_irrational` | `sqrt(2)` | `1.4142135623730951` | `""` | 0 |
| `test_abs` | `abs(-5)` | `5` | `""` | 0 |
| `test_floor` | `floor(2.7)` | `2` | `""` | 0 |
| `test_ceil` | `ceil(2.3)` | `3` | `""` | 0 |
| `test_round_half_up` | `round(2.5)` | `3` | `""` | 0 |
| `test_sin` | `sin(0)` | `0` | `""` | 0 |
| `test_cos` | `cos(0)` | `1` | `""` | 0 |
| `test_log` | `log(1)` | `0` | `""` | 0 |
| `test_exp` | `exp(0)` | `1` | `""` | 0 |
| `test_pow` | `pow(2, 10)` | `1024` | `""` | 0 |
| `test_atan2` | `atan2(1, 1)` | `0.7853981633974483` | `""` | 0 |
| `test_constant_pi` | `pi` | `3.141592653589793` | `""` | 0 |
| `test_constant_e` | `e` | `2.718281828459045` | `""` | 0 |
| `test_constant_in_expr` | `2 * pi` | `6.283185307179586` | `""` | 0 |
| `test_composed_functions` | `sqrt(pow(3, 2) + pow(4, 2))` | `5` | `""` | 0 |
| `test_domain_error_sqrt` | `sqrt(-1)` | `""` | `error: domain error` | 1 |
| `test_domain_error_log` | `log(0)` | `""` | `error: domain error` | 1 |
| `test_unknown_function` | `unknown(5)` | `""` | `error: unknown function: unknown` | 1 |
| `test_wrong_arg_count_sqrt` | `sqrt()` | `""` | `error: wrong number of arguments: sqrt expects 1` | 1 |
| `test_wrong_arg_count_pow` | `pow(2)` | `""` | `error: wrong number of arguments: pow expects 2` | 1 |

**Total new CLI test cases:** 21

---

## Coverage Map: 27 Spec Criteria → Test Files

The spec has 22 observable CLI criteria (16 success + 5 error + 1 `make test`) plus 5 underlying component behaviors (IDENT lexing, Call/Name parsing, registry dispatch, domain error raises, error message strings). The full 27 are distributed as follows:

| Spec criterion / component behavior | test_lexer | test_parser | test_evaluator | test_errors | test_cli |
|---|:---:|:---:|:---:|:---:|:---:|
| IDENT token lexing (sqrt, pi, atan2, multi-char) | ✓ | | | | |
| `1e10` — `e` not tokenized as IDENT | ✓ | | | | |
| Call AST node construction | | ✓ | | | |
| Name AST node construction | | ✓ | | | |
| Nested call: `sqrt(pow(3,2)+pow(4,2))` AST | | ✓ | | | |
| All 12 function dispatch paths (numeric result) | | | ✓ | | |
| Constant dispatch: `pi`, `e` | | | ✓ | | |
| DomainError raised by evaluator | | | ✓ | | |
| UnknownFunction raised + `.name` field | | | ✓ | | |
| WrongArgCount raised + `.name`, `.expected` fields | | | ✓ | | |
| `error_message(DomainError())` | | | | ✓ | |
| `error_message(UnknownFunction("foo"))` | | | | ✓ | |
| `error_message(WrongArgCount("pow", 2))` | | | | ✓ | |
| 16 spec success criteria (CLI boundary) | | | | | ✓ |
| 5 spec error criteria (CLI boundary) | | | | | ✓ |

`make test` passes when all rows above are green. No spec criterion is left with only CLI coverage when a unit layer exists for it.

---

## Duplication Avoidance

- **`sqrt(9) → 3` is tested twice**: evaluator unit (`3.0`) and CLI (`"3"`). This is intentional—the two tests cover different contracts. The evaluator test verifies the numeric result; the CLI test verifies `format_result` integration and the stdout/exit-0 contract. This mirrors the existing `test_evaluator.py:test_evaluate` + `test_cli.py:test_addition` pattern.
- **Error paths are tested three times for parameterized errors** (`test_errors.py` for message string, `test_evaluator.py` for raise + field, `test_cli.py` for CLI output). Each layer tests a distinct contract: message formatting, raise site, and end-to-end routing. This is consistent with how `DivisionByZero` is handled in v0.1.x.
- **Parser tests do not test evaluation.** `parse("sqrt(-1)")` should produce `Call("sqrt", [UnaryOp("-", Number(1.0))])` without error—no parser test should assert that domain errors are raised.
- **IDENT lexing is not re-tested in `test_parser.py`.** Parser tests call `parse(src)` which runs the lexer internally, so IDENT token production is implicitly exercised. Explicit IDENT tests belong only in `test_lexer.py`.

---

## Count Summary

| File | New test cases |
|---|---|
| `test_lexer.py` | ~9 |
| `test_parser.py` | ~8 |
| `test_evaluator.py` | ~21 |
| `test_errors.py` | ~7 |
| `test_cli.py` | 21 |
| **Total** | **~66** |

---

## Answers to Research Questions

**Lexer tests:** Yes, add a parametrized group for IDENT tokens. The `1e10` / `1 e` distinction is the critical edge case and must be an explicit test case.

**Parser tests:** Yes, add `Call` and `Name` node construction tests including the spec's nested-call example. Arity is not checked at parse time; `Call("sqrt", [])` should parse cleanly.

**Evaluator tests:** All 14 function/constant dispatch paths should be covered at the unit level—not just at CLI level. Domain error raises, unknown function raises, and wrong arg count raises all belong here with field assertions.

**CLI tests:** Every one of the 21 explicit spec criteria should have a dedicated `test_cli.py` case. Sampling is insufficient because the CLI layer is where the spec is defined and where integration failures (routing, format_result, exit codes) are caught.

**Error message tests:** `UnknownFunction("foo")`, `UnknownFunction("unknown")`, `WrongArgCount("sqrt", 1)`, `WrongArgCount("pow", 2)`, and `DomainError()` all belong in `test_errors.py`'s parametrize table. CLI tests for these errors check the full pipeline but are not substitutes for the message-contract test in `test_errors.py`.
