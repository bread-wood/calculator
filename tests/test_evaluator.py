import math
from types import MappingProxyType

import pytest

from calc.evaluator import evaluate, execute_statement, format_result, _round_half_away, _DEFAULT_ENV, _CONSTANTS_VALUES
from calc.errors import DivisionByZero, Overflow, DomainError, UnknownFunction, WrongArity, UndefinedVariable, ConstantReassignment, FunctionAlreadyDefined, CannotRedefineBuiltin
from calc.parser import Assignment, BinaryOp, Number, Name, Call, FunctionDef


def eval_expr(s: str) -> float:
    from calc.lexer import Lexer
    from calc.parser import Parser
    return evaluate(Parser(Lexer(s)).parse_program().body[0])


def eval_program(s: str) -> float | None:
    """Execute all statements in s; return result of last expression statement."""
    from calc.lexer import Lexer
    from calc.parser import Parser
    env = dict(_CONSTANTS_VALUES)
    fn_env: dict = {}
    program = Parser(Lexer(s)).parse_program()
    result = None
    for stmt in program.body:
        result = execute_statement(stmt, env, fn_env)
    return result


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


def test_default_env_is_mapping_proxy():
    assert isinstance(_DEFAULT_ENV, MappingProxyType)


def test_default_env_immutable():
    with pytest.raises(TypeError):
        _DEFAULT_ENV["x"] = 1.0


def test_undefined_variable_raised():
    with pytest.raises(UndefinedVariable):
        evaluate(Name("x"), {})


def test_execute_statement_assignment():
    env = {}
    result = execute_statement(Assignment("x", Number(5.0)), env)
    assert result == 5.0
    assert env == {"x": 5.0}


def test_execute_statement_expression():
    result = execute_statement(BinaryOp("+", Number(2.0), Number(3.0)), {})
    assert result == 5.0


def test_execute_statement_constant_reassignment_pi():
    with pytest.raises(ConstantReassignment):
        execute_statement(Assignment("pi", Number(3.0)), dict(_DEFAULT_ENV))


def test_execute_statement_constant_reassignment_e():
    with pytest.raises(ConstantReassignment):
        execute_statement(Assignment("e", Number(1.0)), dict(_DEFAULT_ENV))


# v0.4.0 — user-defined functions

def test_funcdef_stores_in_fn_env():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = BinaryOp("*", Name("x"), Number(2.0))
    result = execute_statement(FunctionDef("f", ["x"], body), env, fn_env)
    assert result is None
    assert "f" in fn_env


def test_funcdef_body_snapshot_excludes_later_fn():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body_f = BinaryOp("*", Name("x"), Number(2.0))
    execute_statement(FunctionDef("f", ["x"], body_f), env, fn_env)
    body_g = BinaryOp("*", Name("x"), Number(3.0))
    execute_statement(FunctionDef("g", ["x"], body_g), env, fn_env)
    assert "g" not in fn_env["f"].available_fns


def test_funcdef_cannot_redefine_builtin():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = Name("x")
    with pytest.raises(CannotRedefineBuiltin):
        execute_statement(FunctionDef("sqrt", ["x"], body), env, fn_env)


def test_funcdef_already_defined():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = Name("x")
    execute_statement(FunctionDef("f", ["x"], body), env, fn_env)
    with pytest.raises(FunctionAlreadyDefined):
        execute_statement(FunctionDef("f", ["x"], body), env, fn_env)


def test_funcdef_forward_reference_rejected():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = Call("g", [Name("x")])
    with pytest.raises(UnknownFunction):
        execute_statement(FunctionDef("f", ["x"], body), env, fn_env)


def test_call_user_fn_single_param():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = BinaryOp("*", Name("x"), Number(2.0))
    execute_statement(FunctionDef("double", ["x"], body), env, fn_env)
    result = evaluate(Call("double", [Number(5.0)]), env, fn_env)
    assert result == 10.0


def test_call_user_fn_multi_param():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = BinaryOp("+", Name("x"), Name("y"))
    execute_statement(FunctionDef("add", ["x", "y"], body), env, fn_env)
    result = evaluate(Call("add", [Number(3.0), Number(4.0)]), env, fn_env)
    assert result == 7.0


def test_call_user_fn_wrong_arity():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = Name("x")
    execute_statement(FunctionDef("f", ["x"], body), env, fn_env)
    with pytest.raises(WrongArity):
        evaluate(Call("f", []), env, fn_env)
    with pytest.raises(WrongArity):
        evaluate(Call("f", [Number(1.0), Number(2.0)]), env, fn_env)


def test_call_user_fn_body_sees_constants():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body = BinaryOp("*", Name("x"), Name("pi"))
    execute_statement(FunctionDef("f", ["x"], body), env, fn_env)
    result = evaluate(Call("f", [Number(2.0)]), env, fn_env)
    assert result == 2.0 * math.pi


def test_call_user_fn_body_excludes_outer_var():
    env = dict(_CONSTANTS_VALUES)
    env["x"] = 99.0
    fn_env = {}
    body = Name("x")
    execute_statement(FunctionDef("f", ["x"], body), env, fn_env)
    result = evaluate(Call("f", [Number(1.0)]), env, fn_env)
    assert result == 1.0


def test_call_user_fn_calls_sibling_fn():
    env = dict(_CONSTANTS_VALUES)
    fn_env = {}
    body_double = BinaryOp("*", Name("x"), Number(2.0))
    execute_statement(FunctionDef("double", ["x"], body_double), env, fn_env)
    body_quad = Call("double", [Call("double", [Name("x")])])
    execute_statement(FunctionDef("quad", ["x"], body_quad), env, fn_env)
    result = evaluate(Call("quad", [Number(3.0)]), env, fn_env)
    assert result == 12.0


# Integration tests

def test_eval_expr_user_fn_roundtrip():
    result = eval_program("def double(x) = x * 2; double(5)")
    assert result == 10.0


def test_eval_expr_user_fn_unknown_at_call():
    with pytest.raises(UnknownFunction):
        eval_program("f(1)")
