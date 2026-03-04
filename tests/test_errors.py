import pytest
from calc.errors import (
    CalcError,
    error_message,
    ExpectedSingleArg,
    EmptyExpression,
    UnexpectedToken,
    UnexpectedEnd,
    DivisionByZero,
    Overflow,
)


@pytest.mark.parametrize(
    "exc_cls,expected",
    [
        (ExpectedSingleArg, "error: expected a single quoted expression"),
        (EmptyExpression, "error: empty expression"),
        (UnexpectedToken, "error: unexpected token"),
        (UnexpectedEnd, "error: unexpected end of expression"),
        (DivisionByZero, "error: division by zero"),
        (Overflow, "error: overflow"),
    ],
)
def test_error_message(exc_cls, expected):
    assert error_message(exc_cls()) == expected


def test_error_message_unknown_subclass():
    class BogusError(CalcError):
        pass

    with pytest.raises(TypeError):
        error_message(BogusError())


def test_all_subclasses_inherit_from_calc_error():
    for cls in (
        ExpectedSingleArg,
        EmptyExpression,
        UnexpectedToken,
        UnexpectedEnd,
        DivisionByZero,
        Overflow,
    ):
        assert issubclass(cls, CalcError)
