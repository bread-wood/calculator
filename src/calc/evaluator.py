import math
from dataclasses import dataclass
from typing import Callable, Optional

from calc.parser import ASTNode, Number, BinaryOp, UnaryOp, Name, Call
from calc.errors import DivisionByZero, Overflow, DomainError, UnknownFunction, WrongArity, UnknownName


@dataclass(frozen=True)
class FunctionEntry:
    name: str
    arity: int
    fn: Callable[..., float]
    domain_check: Optional[Callable[..., bool]] = None


def _round_half_away(x: float) -> float:
    if x >= 0:
        return float(math.floor(x + 0.5))
    else:
        return float(math.ceil(x - 0.5))


FUNCTION_TABLE: list[FunctionEntry] = [
    FunctionEntry("sqrt",  1, math.sqrt,                      lambda x: x >= 0),
    FunctionEntry("abs",   1, math.fabs,                      None),
    FunctionEntry("floor", 1, lambda x: float(math.floor(x)), None),
    FunctionEntry("ceil",  1, lambda x: float(math.ceil(x)),  None),
    FunctionEntry("round", 1, _round_half_away,                None),
    FunctionEntry("sin",   1, math.sin,                       None),
    FunctionEntry("cos",   1, math.cos,                       None),
    FunctionEntry("tan",   1, math.tan,                       None),
    FunctionEntry("log",   1, math.log,                       lambda x: x > 0),
    FunctionEntry("exp",   1, math.exp,                       None),
    FunctionEntry("pow",   2, math.pow,                       None),
    FunctionEntry("atan2", 2, math.atan2,                     None),
]

_FUNCTION_TABLE: dict[str, FunctionEntry] = {e.name: e for e in FUNCTION_TABLE}

_DEFAULT_ENV: dict[str, float] = {
    "pi": math.pi,
    "e":  math.e,
}


def evaluate(node: ASTNode, env: dict[str, float] | None = None) -> float:
    if env is None:
        env = _DEFAULT_ENV

    if isinstance(node, Number):
        return node.value

    if isinstance(node, Name):
        value = env.get(node.name)
        if value is None:
            raise UnknownName(node.name)
        return value

    if isinstance(node, Call):
        entry = _FUNCTION_TABLE.get(node.func)
        if entry is None:
            raise UnknownFunction(node.func)
        if len(node.args) != entry.arity:
            raise WrongArity(node.func, entry.arity)
        evaluated_args = [evaluate(arg, env) for arg in node.args]
        if entry.domain_check is not None and not entry.domain_check(*evaluated_args):
            raise DomainError()
        try:
            result = entry.fn(*evaluated_args)
        except OverflowError:
            raise Overflow()
        _check_overflow(result)
        return result

    if isinstance(node, UnaryOp) and node.op == '-':
        result = -evaluate(node.operand, env)
        _check_overflow(result)
        return result

    if isinstance(node, BinaryOp):
        left = evaluate(node.left, env)
        right = evaluate(node.right, env)
        if node.op == '+':
            result = left + right
        elif node.op == '-':
            result = left - right
        elif node.op == '*':
            result = left * right
        elif node.op == '/':
            if right == 0.0:
                raise DivisionByZero()
            result = left / right
        else:
            raise ValueError(f"Unknown operator: {node.op!r}")
        _check_overflow(result)
        return result

    raise TypeError(f"Unknown node type: {type(node)!r}")


def format_result(value: float) -> str:
    if math.trunc(value) == value:
        return str(int(value))
    return str(value)


def _check_overflow(result: float) -> None:
    if math.isinf(result) or math.isnan(result):
        raise Overflow()
