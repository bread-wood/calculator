import math

import pytest

from calc.evaluator import evaluate, format_result, _round_half_away
from calc.errors import DivisionByZero, Overflow, DomainError, UnknownFunction, WrongArity


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


@pytest.mark.parametrize("expr,expected", [
    ("sqrt(9)",     3.0),
    ("sqrt(2)",     math.sqrt(2)),
    ("abs(-5)",     5.0),
    ("floor(2.7)",  2.0),
    ("ceil(2.3)",   3.0),
    ("round(2.5)",  3.0),
    ("sin(0)",      0.0),
    ("cos(0)",      1.0),
    ("log(1)",      0.0),
    ("exp(0)",      1.0),
    ("pow(2, 10)",  1024.0),
    ("atan2(1, 1)", math.atan2(1, 1)),
    ("pi",          math.pi),
    ("e",           math.e),
])
def test_functions_and_constants(expr, expected):
    assert eval_expr(expr) == expected


def test_domain_error_sqrt():
    with pytest.raises(DomainError):
        eval_expr("sqrt(-1)")


def test_domain_error_log():
    with pytest.raises(DomainError):
        eval_expr("log(0)")


def test_unknown_function():
    with pytest.raises(UnknownFunction):
        eval_expr("unknown(5)")


def test_wrong_arity_sqrt():
    with pytest.raises(WrongArity):
        eval_expr("sqrt()")


def test_wrong_arity_pow():
    with pytest.raises(WrongArity):
        eval_expr("pow(2)")


@pytest.mark.parametrize("x, expected", [
    (2.5, 3.0), (3.5, 4.0), (-2.5, -3.0), (2.4, 2.0), (2.0, 2.0),
])
def test_round_half_away(x, expected):
    assert _round_half_away(x) == expected


@pytest.mark.parametrize("value, expected_str", [
    (3.0,                  "3"),
    (1.4142135623730951,   "1.4142135623730951"),
    (3.141592653589793,    "3.141592653589793"),
    (0.7853981633974483,   "0.7853981633974483"),
])
def test_format_result_decimals(value, expected_str):
    assert format_result(value) == expected_str
