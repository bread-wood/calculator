class CalcError(Exception):
    """Base class for all calculator errors."""

    def description(self) -> str:
        raise AttributeError  # abstract; subclasses must override


class ExpectedSingleArg(CalcError):
    """Raised when argument count != 1 (and != 0, which yields usage)."""

    def description(self) -> str:
        return "expected a single quoted expression"


class EmptyExpression(CalcError):
    """Raised when argv[1] is the empty string."""

    def description(self) -> str:
        return "empty expression"


class UnexpectedToken(CalcError):
    """Raised by lexer (unrecognised character) or parser (valid token in wrong position)."""

    def description(self) -> str:
        return "unexpected token"


class UnexpectedEnd(CalcError):
    """Raised by parser when EOF is encountered where an operand/token was expected."""

    def description(self) -> str:
        return "unexpected end of expression"


class DivisionByZero(CalcError):
    """Raised by evaluator when the right-hand operand of '/' evaluates to zero."""

    def description(self) -> str:
        return "division by zero"


class Overflow(CalcError):
    """Raised by evaluator when the result is infinite or NaN."""

    def description(self) -> str:
        return "overflow"


class DomainError(CalcError):
    def description(self) -> str:
        return "domain error"


class UnknownFunction(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown function '{self.name}'"


class WrongArity(CalcError):
    def __init__(self, name: str, expected: int) -> None:
        self.name = name
        self.expected = expected
        super().__init__(name, expected)

    def description(self) -> str:
        noun = "argument" if self.expected == 1 else "arguments"
        return f"'{self.name}' expects {self.expected} {noun}"


class UnknownName(CalcError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)

    def description(self) -> str:
        return f"unknown name '{self.name}'"


def error_message(e: CalcError) -> str:
    try:
        return f"error: {e.description()}"
    except AttributeError:
        raise TypeError(f"Unknown CalcError subclass: {type(e)!r}") from None
