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
    DomainError,
    UnknownFunction,
    WrongArity,
    UndefinedVariable,
    ConstantReassignment,
    FunctionAlreadyDefined,
    CannotRedefineBuiltin,
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


def test_domain_error_message():
    assert error_message(DomainError()) == "error: domain error"


def test_unknown_function_message():
    assert error_message(UnknownFunction("sqrt")) == "error: undefined function: sqrt"


def test_wrong_arity_singular():
    assert error_message(WrongArity("abs", 1)) == "error: wrong number of arguments: abs expects 1 argument"


def test_wrong_arity_plural():
    assert error_message(WrongArity("pow", 2)) == "error: wrong number of arguments: pow expects 2 arguments"


def test_undefined_variable_message():
    assert error_message(UndefinedVariable("x")) == "error: undefined variable: x"


def test_new_subclasses_inherit_from_calc_error():
    for cls in (DomainError, UnknownFunction, WrongArity, UndefinedVariable, ConstantReassignment):
        assert issubclass(cls, CalcError)


def test_unknown_function_stores_name():
    assert UnknownFunction("foo").name == "foo"


def test_wrong_arity_stores_fields():
    e = WrongArity("pow", 2)
    assert e.name == "pow"
    assert e.expected == 2


def test_undefined_variable_stores_name():
    assert UndefinedVariable("x").name == "x"


def test_undefined_variable_message_pi_approx():
    assert error_message(UndefinedVariable("pi_approx")) == "error: undefined variable: pi_approx"


def test_constant_reassignment_message():
    assert error_message(ConstantReassignment("pi")) == "error: cannot reassign constant: pi"


def test_constant_reassignment_stores_name():
    assert ConstantReassignment("pi").name == "pi"


def test_constant_reassignment_no_quotes_in_message():
    msg = error_message(ConstantReassignment("e"))
    assert "e" in msg
    assert "'e'" not in msg


def test_constant_reassignment_inherits_calc_error():
    assert issubclass(ConstantReassignment, CalcError)


# v0.4.0 — user-defined functions
def test_function_already_defined_message():
    assert error_message(FunctionAlreadyDefined("f")) == "error: function already defined: f"


def test_cannot_redefine_builtin_message():
    assert error_message(CannotRedefineBuiltin("sqrt")) == "error: cannot redefine built-in: sqrt"


def test_unknown_function_no_quotes():
    msg = error_message(UnknownFunction("myFunc"))
    assert "'" not in msg and "myFunc" in msg


def test_wrong_arity_no_quotes_around_name():
    msg = error_message(WrongArity("myFunc", 2))
    assert "'" not in msg and "myFunc" in msg


def test_wrong_arity_new_prefix():
    assert error_message(WrongArity("f", 1)).startswith("error: wrong number of arguments:")


def test_function_already_defined_stores_name():
    assert FunctionAlreadyDefined("g").name == "g"


def test_cannot_redefine_builtin_stores_name():
    assert CannotRedefineBuiltin("sin").name == "sin"


def test_function_already_defined_is_calc_error():
    assert isinstance(FunctionAlreadyDefined("f"), CalcError)


def test_cannot_redefine_builtin_is_calc_error():
    assert isinstance(CannotRedefineBuiltin("sin"), CalcError)


def test_function_already_defined_not_subclass_of_cannot_redefine():
    assert not issubclass(FunctionAlreadyDefined, CannotRedefineBuiltin)


def test_cannot_redefine_not_subclass_of_function_already_defined():
    assert not issubclass(CannotRedefineBuiltin, FunctionAlreadyDefined)
