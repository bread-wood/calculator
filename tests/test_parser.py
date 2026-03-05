import pytest

from calc.errors import UnexpectedEnd, UnexpectedToken
from calc.lexer import Lexer
from calc.parser import BinaryOp, Call, Name, Number, Parser, UnaryOp


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


def test_name_pi():
    assert parse("pi") == Name("pi")


def test_name_e():
    assert parse("e") == Name("e")


def test_call_sqrt():
    assert parse("sqrt(9)") == Call("sqrt", [Number(9.0)])


def test_call_pow():
    assert parse("pow(2, 10)") == Call("pow", [Number(2.0), Number(10.0)])


def test_call_abs():
    assert parse("abs(0)") == Call("abs", [Number(0.0)])


def test_zero_arg_call():
    assert parse("f()") == Call("f", [])


def test_unary_name():
    assert parse("-pi") == UnaryOp("-", Name("pi"))


def test_call_with_expr_arg():
    assert parse("sqrt(2 + 3)") == Call("sqrt", [BinaryOp("+", Number(2.0), Number(3.0))])


def test_nested_calls():
    assert parse("pow(sqrt(4), 2)") == Call("pow", [Call("sqrt", [Number(4.0)]), Number(2.0)])


def test_name_in_binary():
    assert parse("2 * pi") == BinaryOp("*", Number(2.0), Name("pi"))


@pytest.mark.parametrize("expr,error_type", [
    ("sqrt(", UnexpectedEnd),
    ("sqrt(9", UnexpectedEnd),
    ("sqrt(9 4", UnexpectedToken),
])
def test_parse_errors_v0_2_0(expr, error_type):
    with pytest.raises(error_type):
        Parser(Lexer(expr)).parse()


def test_trailing_comma_is_error():
    with pytest.raises((UnexpectedEnd, UnexpectedToken)):
        parse("f(1,)")
