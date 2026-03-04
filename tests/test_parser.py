import pytest

from calc.errors import UnexpectedEnd, UnexpectedToken
from calc.lexer import Lexer
from calc.parser import BinaryOp, Number, Parser, UnaryOp


def parse(expr: str):
    return Parser(Lexer(expr)).parse()


def test_number():
    assert parse("2") == Number(2.0)


def test_addition():
    assert parse("2 + 3") == BinaryOp("+", Number(2.0), Number(3.0))


def test_precedence_mul_over_add():
    assert parse("2 + 3 * 4") == BinaryOp("+", Number(2.0), BinaryOp("*", Number(3.0), Number(4.0)))


def test_grouping():
    assert parse("(2 + 3) * 4") == BinaryOp("*", BinaryOp("+", Number(2.0), Number(3.0)), Number(4.0))


def test_unary_negation():
    assert parse("-5") == UnaryOp("-", Number(5.0))


def test_double_unary_negation():
    assert parse("--5") == UnaryOp("-", UnaryOp("-", Number(5.0)))


def test_binary_with_unary():
    assert parse("2 - -3") == BinaryOp("-", Number(2.0), UnaryOp("-", Number(3.0)))


def test_left_associativity():
    assert parse("2 - 3 - 4") == BinaryOp("-", BinaryOp("-", Number(2.0), Number(3.0)), Number(4.0))


@pytest.mark.parametrize("expr,error_type", [
    ("2 +", UnexpectedEnd),
    ("(2 + 3", UnexpectedEnd),
    ("2 3", UnexpectedToken),
    ("2 + )", UnexpectedToken),
    ("(2 + 3 4", UnexpectedToken),
])
def test_parse_errors(expr, error_type):
    with pytest.raises(error_type):
        Parser(Lexer(expr)).parse()
