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
    DomainError,
    UnknownFunction,
    WrongArity,
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


# v0.2.0 acceptance tests

def test_sqrt_integer():
    r = run_calc("sqrt(9)")
    assert r.returncode == 0
    assert r.stdout.strip() == "3"
    assert r.stderr == ""


def test_sqrt_irrational():
    r = run_calc("sqrt(2)")
    assert r.returncode == 0
    assert r.stdout.strip() == "1.4142135623730951"
    assert r.stderr == ""


def test_abs():
    r = run_calc("abs(-5)")
    assert r.returncode == 0
    assert r.stdout.strip() == "5"
    assert r.stderr == ""


def test_floor():
    r = run_calc("floor(2.7)")
    assert r.returncode == 0
    assert r.stdout.strip() == "2"
    assert r.stderr == ""


def test_ceil():
    r = run_calc("ceil(2.3)")
    assert r.returncode == 0
    assert r.stdout.strip() == "3"
    assert r.stderr == ""


def test_round():
    r = run_calc("round(2.5)")
    assert r.returncode == 0
    assert r.stdout.strip() == "3"
    assert r.stderr == ""


def test_sin():
    r = run_calc("sin(0)")
    assert r.returncode == 0
    assert r.stdout.strip() == "0"
    assert r.stderr == ""


def test_cos():
    r = run_calc("cos(0)")
    assert r.returncode == 0
    assert r.stdout.strip() == "1"
    assert r.stderr == ""


def test_log():
    r = run_calc("log(1)")
    assert r.returncode == 0
    assert r.stdout.strip() == "0"
    assert r.stderr == ""


def test_exp():
    r = run_calc("exp(0)")
    assert r.returncode == 0
    assert r.stdout.strip() == "1"
    assert r.stderr == ""


def test_pow():
    r = run_calc("pow(2, 10)")
    assert r.returncode == 0
    assert r.stdout.strip() == "1024"
    assert r.stderr == ""


def test_atan2():
    r = run_calc("atan2(1, 1)")
    assert r.returncode == 0
    assert r.stdout.strip() == "0.7853981633974483"
    assert r.stderr == ""


def test_pi():
    r = run_calc("pi")
    assert r.returncode == 0
    assert r.stdout.strip() == "3.141592653589793"
    assert r.stderr == ""


def test_e():
    r = run_calc("e")
    assert r.returncode == 0
    assert r.stdout.strip() == "2.718281828459045"
    assert r.stderr == ""


def test_two_pi():
    r = run_calc("2 * pi")
    assert r.returncode == 0
    assert r.stdout.strip() == "6.283185307179586"
    assert r.stderr == ""


def test_nested_calls():
    r = run_calc("sqrt(pow(3, 2) + pow(4, 2))")
    assert r.returncode == 0
    assert r.stdout.strip() == "5"
    assert r.stderr == ""


def test_domain_error_sqrt():
    r = run_calc("sqrt(-1)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(DomainError())


def test_domain_error_log():
    r = run_calc("log(0)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(DomainError())


def test_unknown_function():
    r = run_calc("unknown(5)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(UnknownFunction("unknown"))


def test_wrong_arity_sqrt():
    r = run_calc("sqrt()")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(WrongArity("sqrt", 1))


def test_wrong_arity_pow():
    r = run_calc("pow(2)")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.strip() == error_message(WrongArity("pow", 2))
