import math

from calc.parser import ASTNode, Number, BinaryOp, UnaryOp
from calc.errors import DivisionByZero, Overflow


def evaluate(node: ASTNode) -> float:
    if isinstance(node, Number):
        return node.value

    if isinstance(node, UnaryOp) and node.op == '-':
        result = -evaluate(node.operand)
        _check_overflow(result)
        return result

    if isinstance(node, BinaryOp):
        left = evaluate(node.left)
        right = evaluate(node.right)
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
    s = f"{value:.15g}"
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def _check_overflow(result: float) -> None:
    if math.isinf(result) or math.isnan(result):
        raise Overflow()
