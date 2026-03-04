class CalcError(Exception):
    """Base class for all calculator errors."""


class ExpectedSingleArg(CalcError):
    """Raised when argument count != 1 (and != 0, which yields usage)."""


class EmptyExpression(CalcError):
    """Raised when argv[1] is the empty string."""


class UnexpectedToken(CalcError):
    """Raised by lexer (unrecognised character) or parser (valid token in wrong position)."""


class UnexpectedEnd(CalcError):
    """Raised by parser when EOF is encountered where an operand/token was expected."""


class DivisionByZero(CalcError):
    """Raised by evaluator when the right-hand operand of '/' evaluates to zero."""


class Overflow(CalcError):
    """Raised by evaluator when the result is infinite or NaN."""


_MESSAGES: dict[type[CalcError], str] = {
    ExpectedSingleArg: "expected a single quoted expression",
    EmptyExpression: "empty expression",
    UnexpectedToken: "unexpected token",
    UnexpectedEnd: "unexpected end of expression",
    DivisionByZero: "division by zero",
    Overflow: "overflow",
}


def error_message(e: CalcError) -> str:
    description = _MESSAGES.get(type(e))
    if description is None:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}")
    return f"error: {description}"
