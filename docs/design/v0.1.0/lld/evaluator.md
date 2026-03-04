# Low-Level Design — Evaluator Module (v0.1.0)

**Milestone:** v0.1.0
**Date:** 2026-03-04
**Status:** Draft
**File:** `src/calc/evaluator.py`

---

## 1. Responsibilities

The evaluator module has two responsibilities:

1. **Tree-walk evaluation** — recursively traverse the AST produced by the parser and compute a `float` result, raising `CalcError` subclasses on arithmetic errors.
2. **Result formatting** — convert a `float` result to a string, suppressing trailing `.0` for whole numbers and trailing zeros for decimals.

---

## 2. Data Structures

### 2.1 AST Node Types (imported from `parser.py`)

The evaluator consumes AST nodes defined in `src/calc/parser.py`. The exact node representation is specified in the parser LLD; the evaluator treats them as Python dataclasses with the following fields:

```python
@dataclass
class Number:
    value: float          # pre-parsed float from lexer token

@dataclass
class BinaryOp:
    op: str               # one of: '+', '-', '*', '/'
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp:
    op: str               # '-'
    operand: ASTNode

ASTNode = Number | BinaryOp | UnaryOp
```

The evaluator imports `Number`, `BinaryOp`, `UnaryOp` from `parser.py` only. No other parser internals are imported.

### 2.2 Return Type

`evaluate(node: ASTNode) -> float`

A plain Python `float` (IEEE 754 double precision, 64-bit). No wrapper type is used.

---

## 3. Public API

```python
# src/calc/evaluator.py

def evaluate(node: ASTNode) -> float:
    """
    Recursively evaluate an AST node and return a float result.

    Raises:
        DivisionByZero  — if a division by zero is attempted
        Overflow        — if the result is infinite or NaN
    """

def format_result(value: float) -> str:
    """
    Convert a float to its canonical string representation.

    Rules:
    - Whole numbers (value == math.trunc(value)): return str(int(value))
    - Fractional numbers: return shortest decimal with no trailing zeros,
      no scientific notation.

    Examples:
        format_result(5.0)   -> "5"
        format_result(2.5)   -> "2.5"
        format_result(2.0)   -> "2"
        format_result(-3.0)  -> "-3"
        format_result(0.1)   -> "0.1"
    """
```

`format_result` lives in `evaluator.py`. Placement decision: it is a pure function operating on a `float`; it has no dependency on the parser or lexer, and placing it here keeps the evaluator module self-contained and independently testable. `__main__.py` calls it after `evaluate()`.

---

## 4. Key Algorithms

### 4.1 Tree-Walk Evaluation

```
evaluate(node):
    if node is Number:
        return node.value

    if node is UnaryOp:
        operand = evaluate(node.operand)
        if node.op == '-':
            result = -operand
        check_overflow(result)
        return result

    if node is BinaryOp:
        left  = evaluate(node.left)
        right = evaluate(node.right)

        if node.op == '+':
            result = left + right
        elif node.op == '-':
            result = left - right
        elif node.op == '*':
            result = left * right
        elif node.op == '/':
            if right == 0.0:
                raise DivisionByZero()
            result = left / right

        check_overflow(result)
        return result

check_overflow(result):
    if math.isinf(result) or math.isnan(result):
        raise Overflow()
```

**Division-by-zero check**: The denominator is compared to `0.0` before the division. This prevents IEEE 754 silent infinity (`1.0 / 0.0 → inf`) from bypassing the error. The check uses `right == 0.0`; Python does not raise on float division by zero but yields `inf`.

**NaN handling decision**: `math.isnan` is checked alongside `math.isinf` inside `check_overflow`. NaN arises from `0.0 / 0.0` in IEEE 754; the division-by-zero pre-check prevents this case from reaching the NaN guard for the standard `0 / 0` input. However, if future operands can produce NaN through other means, the guard ensures they are caught. Both conditions map to `Overflow` (a single error variant is sufficient for v0.1.0; NaN is not a distinct user-visible error category per the spec).

**Overflow check placement**: Applied after every arithmetic operation (including unary negation on the result). Not applied to bare `Number` nodes; the lexer/parser are responsible for rejecting unparseable literals.

### 4.2 Output Formatting

```
format_result(value):
    if math.trunc(value) == value:
        return str(int(value))
    else:
        # Python's repr/str of float gives shortest round-trip representation
        # with no trailing zeros for common values.
        # Use format(value, 'f') stripped of trailing zeros for safety.
        s = f"{value:.15g}"  # up to 15 significant digits, no sci notation for normal range
        # strip trailing zeros after decimal point
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
            # but we need the decimal point back if fractional
            if '.' not in s and '.' was in original:
                pass  # rstrip('.') already removed it only if no fraction remains
        return s
```

**Concrete Python implementation:**

```python
import math

def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    # Use %g with 15 significant digits to avoid scientific notation for
    # values in the normal calculator range, then strip trailing zeros.
    s = f"{value:.15g}"
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s
```

The `math.trunc(value) == value` check handles both positive and negative whole numbers correctly (`math.trunc(-3.0) == -3.0 → True`). `math.floor` would fail for negative non-integer values.

The `:.15g` format uses up to 15 significant digits. For the calculator's expected input range (human-typed arithmetic), scientific notation is not triggered. If a result like `1e20` were produced, `:.15g` would emit `1e+20`; this is an edge case outside the v0.1.0 spec and is acceptable.

---

## 5. Error Handling

### 5.1 Errors raised by the evaluator

| Condition | Exception class | Message (from `errors.py`) |
|---|---|---|
| Denominator is `0.0` before division | `DivisionByZero` | `error: division by zero` |
| Result is `math.isinf` or `math.isnan` after any operation | `Overflow` | `error: overflow` |

### 5.2 Contract

- The evaluator never writes to `stderr`.
- The evaluator never calls `sys.exit`.
- All errors are raised as `CalcError` subclass instances and propagate to `__main__.py`.
- The evaluator assumes that `node` is a well-formed AST (produced by a successful `Parser.parse()` call). It does not re-validate token types or grammar.
- If `node` is of an unexpected type (programming error, not user error), a bare Python `TypeError` will propagate naturally; no special handling is defined.

### 5.3 Error class imports

```python
from calc.errors import DivisionByZero, Overflow
```

---

## 6. Module Interface Summary

```python
# src/calc/evaluator.py

import math
from calc.parser import ASTNode, Number, BinaryOp, UnaryOp
from calc.errors import DivisionByZero, Overflow

def evaluate(node: ASTNode) -> float: ...
def format_result(value: float) -> str: ...
```

No classes are defined in this module. Both exported names are module-level functions. The module has no global state.

---

## 7. Test Strategy

File: `tests/test_evaluator.py`

### 7.1 `evaluate()` — arithmetic correctness

Use `pytest.mark.parametrize` over a table of `(expression_string, expected_float)` pairs. Each test builds an AST by calling `Parser(Lexer(expr)).parse()` and passes it to `evaluate()`.

| Expression | Expected |
|---|---|
| `"2 + 3"` | `5.0` |
| `"10 / 4"` | `2.5` |
| `"2 + 3 * 4"` | `14.0` |
| `"(2 + 3) * 4"` | `20.0` |
| `"4 / 2"` | `2.0` |
| `"-5"` | `-5.0` |
| `"-(2 + 3)"` | `-5.0` |
| `"1 - -1"` | `2.0` |

### 7.2 `evaluate()` — error cases

| Expression | Expected exception |
|---|---|
| `"1 / 0"` | `DivisionByZero` |
| `"0 / 0"` | `DivisionByZero` |
| `"1e308 * 10"` | `Overflow` |

Verify that the correct `CalcError` subclass is raised using `pytest.raises(DivisionByZero)` etc. Do not assert on message strings in evaluator unit tests; message strings are verified in CLI integration tests.

### 7.3 `format_result()` — formatting

Test the formatter in isolation with direct float inputs:

| Input | Expected output |
|---|---|
| `5.0` | `"5"` |
| `2.5` | `"2.5"` |
| `2.0` | `"2"` |
| `-3.0` | `"-3"` |
| `0.0` | `"0"` |
| `0.1` | `"0.1"` |
| `10.0 / 4.0` (i.e. `2.5`) | `"2.5"` |

### 7.4 Coverage targets

- All four binary operators (including division).
- Unary negation.
- Nested expressions (parentheses, multiple levels).
- Both error variants (`DivisionByZero`, `Overflow`).
- All `format_result` categories (whole positive, whole negative, zero, fractional).

### 7.5 Test file skeleton

```python
import math
import pytest
from calc.lexer import Lexer
from calc.parser import Parser
from calc.evaluator import evaluate, format_result
from calc.errors import DivisionByZero, Overflow

def eval_expr(s: str) -> float:
    return evaluate(Parser(Lexer(s)).parse())

@pytest.mark.parametrize("expr,expected", [
    ("2 + 3", 5.0),
    ("10 / 4", 2.5),
    ("2 + 3 * 4", 14.0),
    ("(2 + 3) * 4", 20.0),
    ("4 / 2", 2.0),
    ("-5", -5.0),
    ("-(2 + 3)", -5.0),
    ("1 - -1", 2.0),
])
def test_evaluate(expr, expected):
    assert eval_expr(expr) == expected

def test_division_by_zero():
    with pytest.raises(DivisionByZero):
        eval_expr("1 / 0")

def test_overflow():
    with pytest.raises(Overflow):
        eval_expr("1e308 * 10")

@pytest.mark.parametrize("value,expected", [
    (5.0,   "5"),
    (2.5,   "2.5"),
    (2.0,   "2"),
    (-3.0,  "-3"),
    (0.0,   "0"),
    (0.1,   "0.1"),
])
def test_format_result(value, expected):
    assert format_result(value) == expected
```

---

## 8. Open Questions Resolved

| Question (from HLD) | Decision |
|---|---|
| `format_result` location | Lives in `evaluator.py`. It is a pure arithmetic helper with no deps beyond `math`; keeping it in the evaluator module avoids an extra utility file. |
| NaN handling | `math.isnan` is checked in `check_overflow` alongside `math.isinf`. Both map to `Overflow`. The division-by-zero pre-check already prevents `0/0` from reaching the NaN path, but the guard is retained for correctness. |

---

## 9. Dependencies

| Dependency | Direction |
|---|---|
| `calc.parser` | imports `Number`, `BinaryOp`, `UnaryOp`, `ASTNode` |
| `calc.errors` | imports `DivisionByZero`, `Overflow` |
| `math` (stdlib) | `math.isinf`, `math.isnan`, `math.trunc` |

No dependency on `calc.lexer` or `calc.__main__`.
