import subprocess
import sys

from calc.errors import (
    error_message,
    ExpectedSingleArg,
    EmptyExpression,
    UnexpectedToken,
    UnexpectedEnd,
    DivisionByZero,
    Overflow,
)


def run_calc(*args):
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True,
        text=True,
    )


def test_addition():
    r = run_calc("2 + 3")
    assert r.stdout.strip() == "5"
    assert r.stderr == ""
    assert r.returncode == 0


def test_division_fractional():
    r = run_calc("10 / 4")
    assert r.stdout.strip() == "2.5"
    assert r.stderr == ""
    assert r.returncode == 0


def test_precedence():
    r = run_calc("2 + 3 * 4")
    assert r.stdout.strip() == "14"
    assert r.stderr == ""
    assert r.returncode == 0


def test_grouping():
    r = run_calc("(2 + 3) * 4")
    assert r.stdout.strip() == "20"
    assert r.stderr == ""
    assert r.returncode == 0


def test_integer_output():
    r = run_calc("4 / 2")
    assert r.stdout.strip() == "2"
    assert r.stderr == ""
    assert r.returncode == 0


def test_no_args():
    r = run_calc()
    assert r.stdout == ""
    assert "usage" in r.stderr
    assert r.returncode == 1


def test_too_many_args():
    r = run_calc("1", "2")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(ExpectedSingleArg())
    assert r.returncode == 1


def test_empty_expression():
    r = run_calc("")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(EmptyExpression())
    assert r.returncode == 1


def test_unexpected_token():
    r = run_calc("@")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(UnexpectedToken())
    assert r.returncode == 1


def test_unexpected_end():
    r = run_calc("2 +")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(UnexpectedEnd())
    assert r.returncode == 1


def test_division_by_zero():
    r = run_calc("1 / 0")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(DivisionByZero())
    assert r.returncode == 1


def test_overflow():
    r = run_calc("1e308 * 1e308")
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(Overflow())
    assert r.returncode == 1


# v0.3.0 multi-statement tests

def test_variable_assignment():
    r = run_calc("x = 5")
    assert r.stdout.strip() == "5"
    assert r.stderr == ""
    assert r.returncode == 0


def test_variable_reference():
    r = run_calc("x = 5; x + 1")
    assert r.stdout.strip() == "6"
    assert r.stderr == ""
    assert r.returncode == 0


def test_multi_statement():
    r = run_calc("x = 5; y = x * 2; y + 1")
    assert r.stdout.strip() == "11"
    assert r.stderr == ""
    assert r.returncode == 0


def test_last_stmt_is_assignment():
    r = run_calc("x = 3; y = 4")
    assert r.stdout.strip() == "4"
    assert r.stderr == ""
    assert r.returncode == 0


def test_trailing_semicolon():
    r = run_calc("x = 5;")
    assert r.stdout.strip() == "5"
    assert r.stderr == ""
    assert r.returncode == 0


def test_constant_pi_readable():
    r = run_calc("pi * 2")
    assert r.stdout.strip() == "6.283185307179586"
    assert r.stderr == ""
    assert r.returncode == 0


def test_constant_e_readable():
    r = run_calc("e")
    assert r.stdout.strip() == "2.718281828459045"
    assert r.stderr == ""
    assert r.returncode == 0


def test_constant_reassignment_pi():
    r = run_calc("pi = 3")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: cannot reassign constant: pi"
    assert r.returncode == 1


def test_constant_reassignment_e():
    r = run_calc("e = 1")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: cannot reassign constant: e"
    assert r.returncode == 1


def test_undefined_variable():
    r = run_calc("x + 1")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: undefined variable: x"
    assert r.returncode == 1


def test_error_in_second_statement():
    r = run_calc("x = 1; x / 0")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: division by zero"
    assert r.returncode == 1


def test_integer_result_from_variable():
    r = run_calc("x = 4; x / 2")
    assert r.stdout.strip() == "2"
    assert r.stderr == ""
    assert r.returncode == 0


# v0.4.0 — user-defined functions

def test_function_definition_no_output():
    r = run_calc("def f(x) = x * 2")
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_call_single_arg():
    r = run_calc("def f(x) = x * 2; f(5)")
    assert r.stdout.strip() == "10"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_call_multi_param():
    r = run_calc("def f(x, y) = x + y; f(3, 4)")
    assert r.stdout.strip() == "7"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_body_uses_constant_pi():
    r = run_calc("def f(x) = x * pi; f(2)")
    assert r.stdout.strip() == "6.283185307179586"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_call_result_in_expression():
    r = run_calc("def f(x) = x; 1 + f(2)")
    assert r.stdout.strip() == "3"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_composed_calls():
    r = run_calc("def f(x) = x + 1; def g(x) = f(x) * 2; g(3)")
    assert r.stdout.strip() == "8"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_zero_params():
    r = run_calc("def f() = 42; f()")
    assert r.stdout.strip() == "42"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_definition_and_variable():
    r = run_calc("x = 3; def f(n) = n * 2; f(x)")
    assert r.stdout.strip() == "6"
    assert r.stderr == ""
    assert r.returncode == 0


def test_multiple_definitions_no_output():
    r = run_calc("def f(x) = x; def g(x) = x * 2")
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_call_decimal_result():
    r = run_calc("def half(x) = x / 2; half(3)")
    assert r.stdout.strip() == "1.5"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_body_uses_builtin():
    r = run_calc("def mysqrt(x) = sqrt(x); mysqrt(9)")
    assert r.stdout.strip() == "3"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_result_is_integer_formatted():
    r = run_calc("def f(x) = x * 2; f(3)")
    assert r.stdout.strip() == "6"
    assert r.stderr == ""
    assert r.returncode == 0


def test_function_definition_error_already_defined():
    r = run_calc("def f() = 1; def f() = 2")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: function already defined: f"
    assert r.returncode == 1


def test_function_definition_error_redefine_builtin():
    r = run_calc("def sqrt(x) = x")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: cannot redefine built-in: sqrt"
    assert r.returncode == 1


def test_function_call_error_wrong_arity():
    r = run_calc("def f(x) = x; f(1, 2)")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: wrong number of arguments: f expects 1 argument"
    assert r.returncode == 1


def test_function_call_error_undefined_function():
    r = run_calc("g(1)")
    assert r.stdout == ""
    assert r.stderr.strip() == "error: undefined function: g"
    assert r.returncode == 1


def test_subcommand_routing_smoke(tmp_path):
    """'plot' keyword routes to the plot subcommand, not legacy eval."""
    import subprocess
    import sys
    out = tmp_path / "smoke.png"
    result = subprocess.run(
        [sys.executable, "-m", "calc", "plot", "x", "--output", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert out.exists()
