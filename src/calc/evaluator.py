import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from calc.parser import ASTNode, Number, BinaryOp, UnaryOp, Name, Call, Assignment, Statement, FunctionDef
from calc.errors import (
    DivisionByZero, Overflow, DomainError, UnknownFunction, WrongArity,
    UndefinedVariable, ConstantReassignment, FunctionAlreadyDefined, CannotRedefineBuiltin,
)


def _round_half_away(x: float) -> float:
    return float(math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5))


@dataclass(frozen=True)
class FunctionEntry:
    name: str
    arity: int
    fn: Callable[..., float]
    domain_check: Callable[..., bool] | None = None


_FUNCTION_LIST: list[FunctionEntry] = [
    FunctionEntry("sqrt",  1, math.sqrt,                          lambda x: x >= 0),
    FunctionEntry("abs",   1, math.fabs,                          None),
    FunctionEntry("floor", 1, lambda x: float(math.floor(x)),    None),
    FunctionEntry("ceil",  1, lambda x: float(math.ceil(x)),     None),
    FunctionEntry("round", 1, _round_half_away,                   None),
    FunctionEntry("sin",   1, math.sin,                           None),
    FunctionEntry("cos",   1, math.cos,                           None),
    FunctionEntry("tan",   1, math.tan,                           None),
    FunctionEntry("log",   1, math.log,                           lambda x: x > 0),
    FunctionEntry("exp",   1, math.exp,                           None),
    FunctionEntry("pow",   2, math.pow,                           None),
    FunctionEntry("atan2", 2, math.atan2,                         None),
]

_FUNCTION_TABLE: dict[str, FunctionEntry] = {e.name: e for e in _FUNCTION_LIST}

_CONSTANTS_VALUES: dict[str, float] = {"pi": math.pi, "e": math.e}

_CONSTANTS: frozenset[str] = frozenset(_CONSTANTS_VALUES)

_DEFAULT_ENV: MappingProxyType = MappingProxyType(dict(_CONSTANTS_VALUES))


@dataclass(frozen=True)
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode
    available_fns: dict[str, "UserFunction"]


def evaluate(node: ASTNode, env: dict[str, float] | None = None, fn_env: dict[str, UserFunction] | None = None) -> float:
    if env is None:
        env = _DEFAULT_ENV
    if fn_env is None:
        fn_env = {}

    if isinstance(node, Number):
        return node.value

    if isinstance(node, UnaryOp) and node.op == '-':
        result = -evaluate(node.operand, env, fn_env)
        _check_overflow(result)
        return result

    if isinstance(node, BinaryOp):
        left = evaluate(node.left, env, fn_env)
        right = evaluate(node.right, env, fn_env)
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

    if isinstance(node, Name):
        if node.name not in env:
            raise UndefinedVariable(node.name)
        return env[node.name]

    if isinstance(node, Call):
        if node.func in fn_env:
            return _call_user_fn(fn_env[node.func], node.args, env, fn_env)
        if node.func not in _FUNCTION_TABLE:
            raise UnknownFunction(node.func)
        entry = _FUNCTION_TABLE[node.func]
        if len(node.args) != entry.arity:
            raise WrongArity(node.func, entry.arity)
        evaled_args = [evaluate(a, env, fn_env) for a in node.args]
        if entry.domain_check is not None and not entry.domain_check(*evaled_args):
            raise DomainError()
        try:
            result = entry.fn(*evaled_args)
        except OverflowError:
            raise Overflow()
        return result

    raise TypeError(f"Unknown node type: {type(node)!r}")


def execute_statement(stmt: Statement, env: dict[str, float], fn_env: dict[str, UserFunction] | None = None) -> float | None:
    if fn_env is None:
        fn_env = {}
    if isinstance(stmt, FunctionDef):
        if stmt.name in _FUNCTION_TABLE:
            raise CannotRedefineBuiltin(stmt.name)
        if stmt.name in fn_env:
            raise FunctionAlreadyDefined(stmt.name)
        _validate_body_calls(stmt.body, fn_env)
        fn_env[stmt.name] = UserFunction(
            name=stmt.name,
            params=stmt.params,
            body=stmt.body,
            available_fns=dict(fn_env),
        )
        return None
    if isinstance(stmt, Assignment):
        if stmt.name in _CONSTANTS:
            raise ConstantReassignment(stmt.name)
        value = evaluate(stmt.value, env, fn_env)
        env[stmt.name] = value
        return value
    return evaluate(stmt, env, fn_env)


def _call_user_fn(uf: UserFunction, args: list[ASTNode], env: dict[str, float], fn_env: dict[str, UserFunction]) -> float:
    if len(args) != len(uf.params):
        raise WrongArity(uf.name, len(uf.params))
    evaled_args = [evaluate(a, env, fn_env) for a in args]
    body_env: dict[str, float] = dict(_CONSTANTS_VALUES)
    body_env.update(zip(uf.params, evaled_args))
    return evaluate(uf.body, body_env, uf.available_fns)


def _validate_body_calls(node: ASTNode, available_fns: dict[str, UserFunction]) -> None:
    if isinstance(node, (Number, Name)):
        return
    if isinstance(node, UnaryOp):
        _validate_body_calls(node.operand, available_fns)
    elif isinstance(node, BinaryOp):
        _validate_body_calls(node.left, available_fns)
        _validate_body_calls(node.right, available_fns)
    elif isinstance(node, Call):
        if node.func not in _FUNCTION_TABLE and node.func not in available_fns:
            raise UnknownFunction(node.func)
        for arg in node.args:
            _validate_body_calls(arg, available_fns)


def format_result(value: float) -> str:
    if value == int(value) and not math.isinf(value):
        return str(int(value))
    return str(value)


def _check_overflow(result: float) -> None:
    if math.isinf(result) or math.isnan(result):
        raise Overflow()
