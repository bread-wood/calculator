import pytest

from calc.evaluator import evaluate, format_result
from calc.errors import DivisionByZero, Overflow


def eval_expr(s: str) -> float:
    from calc.lexer import Lexer
    from calc.parser import Parser
    return evaluate(Parser(Lexer(s)).parse())


@pytest.mark.parametrize("expr,expected", [
    ("2 + 3",       5.0),
    ("10 / 4",      2.5),
    ("2 + 3 * 4",   14.0),
    ("(2 + 3) * 4", 20.0),
    ("4 / 2",       2.0),
    ("-5",          -5.0),
    ("-(2 + 3)",    -5.0),
    ("1 - -1",      2.0),
])
def test_evaluate(expr, expected):
    assert eval_expr(expr) == expected


def test_division_by_zero():
    with pytest.raises(DivisionByZero):
        eval_expr("1 / 0")


def test_division_by_zero_zero_divided():
    with pytest.raises(DivisionByZero):
        eval_expr("0 / 0")


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
