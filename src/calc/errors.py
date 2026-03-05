class CalcError(Exception):
    """Base class for all calculator errors."""


class ExpectedSingleArg(CalcError):
    def description(self) -> str:
        return "expected a single quoted expression"


class EmptyExpression(CalcError):
    def description(self) -> str:
        return "empty expression"


class UnexpectedToken(CalcError):
    def description(self) -> str:
        return "unexpected token"


class UnexpectedEnd(CalcError):
    def description(self) -> str:
        return "unexpected end of expression"


class DivisionByZero(CalcError):
    def description(self) -> str:
        return "division by zero"


class Overflow(CalcError):
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
