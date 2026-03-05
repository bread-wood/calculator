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
    r = run_calc("abc")
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
