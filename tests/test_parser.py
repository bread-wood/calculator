import pytest

from calc.errors import UnexpectedEnd, UnexpectedToken
from calc.lexer import Lexer
from calc.parser import Assignment, BinaryOp, Call, FunctionDef, Name, Number, Parser, Program, UnaryOp


def parse(expr: str):
    return Parser(Lexer(expr)).parse_program().body[0]


def parse_program(expr: str) -> Program:
    return Parser(Lexer(expr)).parse_program()


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
        parse_program(expr)


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
        parse_program(expr)


def test_trailing_comma_is_error():
    with pytest.raises((UnexpectedEnd, UnexpectedToken)):
        parse_program("f(1,)")


# New v0.3.0 tests

def test_assignment_simple():
    prog = parse_program("x = 5")
    assert prog == Program(body=[Assignment("x", Number(5.0))])


def test_assignment_then_expression():
    prog = parse_program("x = 5; x + 1")
    assert prog == Program(body=[
        Assignment("x", Number(5.0)),
        BinaryOp("+", Name("x"), Number(1.0)),
    ])


def test_ident_without_equals_is_name_not_assignment():
    prog = parse_program("x + 1")
    assert prog == Program(body=[BinaryOp("+", Name("x"), Number(1.0))])


def test_trailing_semicolon_accepted():
    prog = parse_program("x = 5;")
    assert prog == Program(body=[Assignment("x", Number(5.0))])


def test_trailing_semicolon_multi_stmt():
    prog = parse_program("x = 5; y = 3;")
    assert prog == Program(body=[
        Assignment("x", Number(5.0)),
        Assignment("y", Number(3.0)),
    ])


def test_three_statements():
    prog = parse_program("x = 5; y = x * 2; y + 1")
    assert prog == Program(body=[
        Assignment("x", Number(5.0)),
        Assignment("y", BinaryOp("*", Name("x"), Number(2.0))),
        BinaryOp("+", Name("y"), Number(1.0)),
    ])


@pytest.mark.parametrize("expr,error_type", [
    ("x =", UnexpectedEnd),
    ("x = )", UnexpectedToken),
    ("x = 5 y = 3", UnexpectedToken),
])
def test_assignment_errors(expr, error_type):
    with pytest.raises(error_type):
        parse_program(expr)


def test_assignment_sqrt():
    prog = parse_program("x = sqrt(9)")
    assert prog == Program(body=[Assignment("x", Call("sqrt", [Number(9.0)]))])


def test_assignment_negative():
    prog = parse_program("x = -5")
    assert prog == Program(body=[Assignment("x", UnaryOp("-", Number(5.0)))])


def test_expression_only():
    prog = parse_program("2 + 3")
    assert prog == Program(body=[BinaryOp("+", Number(2.0), Number(3.0))])


def test_assignment_with_expr_rhs():
    prog = parse_program("x = 5; y = x * 2")
    assert prog == Program(body=[
        Assignment("x", Number(5.0)),
        Assignment("y", BinaryOp("*", Name("x"), Number(2.0))),
    ])


# v0.4.0 — user-defined functions

def test_funcdef_no_params():
    prog = parse_program("def f() = 1")
    assert prog.body[0] == FunctionDef(name="f", params=[], body=Number(1.0))


def test_funcdef_one_param():
    prog = parse_program("def f(x) = x")
    assert prog.body[0] == FunctionDef(name="f", params=["x"], body=Name("x"))


def test_funcdef_multi_params():
    prog = parse_program("def f(x, y) = x + y")
    assert prog.body[0] == FunctionDef(
        name="f", params=["x", "y"], body=BinaryOp("+", Name("x"), Name("y"))
    )


def test_funcdef_body_expression():
    prog = parse_program("def g(x) = x * 2 + 1")
    assert prog.body[0] == FunctionDef(
        name="g",
        params=["x"],
        body=BinaryOp("+", BinaryOp("*", Name("x"), Number(2.0)), Number(1.0)),
    )


def test_funcdef_followed_by_call():
    prog = parse_program("def f(x) = x; f(3)")
    assert prog.body[0] == FunctionDef(name="f", params=["x"], body=Name("x"))
    assert prog.body[1] == Call(func="f", args=[Number(3.0)])


def test_call_in_expression():
    assert parse("f(1) + 2") == BinaryOp("+", Call("f", [Number(1.0)]), Number(2.0))


def test_funcdef_body_uses_call():
    prog = parse_program("def h(x) = sqrt(x)")
    assert prog.body[0] == FunctionDef(
        name="h", params=["x"], body=Call("sqrt", [Name("x")])
    )


def test_funcdef_missing_name():
    with pytest.raises(UnexpectedToken):
        parse_program("def (x) = 1")


def test_funcdef_missing_lparen():
    with pytest.raises(UnexpectedToken):
        parse_program("def f x) = 1")


def test_funcdef_non_ident_param():
    with pytest.raises(UnexpectedToken):
        parse_program("def f(x + 1) = x")


def test_funcdef_missing_rparen():
    with pytest.raises((UnexpectedToken, UnexpectedEnd)):
        parse_program("def f(x = 1")


def test_funcdef_missing_equals():
    with pytest.raises((UnexpectedToken, UnexpectedEnd)):
        parse_program("def f(x) 1")


def test_funcdef_empty_body():
    with pytest.raises(UnexpectedEnd):
        parse_program("def f(x) =")
