import sys

from calc.errors import CalcError, ExpectedSingleArg, EmptyExpression, error_message
from calc.lexer import Lexer
from calc.parser import Parser
from calc.evaluator import execute_statement, format_result, _DEFAULT_ENV, UserFunction


def main() -> None:
    # 1. Argument count check
    if len(sys.argv) == 1:
        print("usage: calc '<expression>'", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) != 2:
        print(error_message(ExpectedSingleArg()), file=sys.stderr)
        sys.exit(1)

    expression = sys.argv[1]

    # 2. Empty-string check
    if expression == "":
        print(error_message(EmptyExpression()), file=sys.stderr)
        sys.exit(1)

    # 3. Pipeline
    try:
        lexer = Lexer(expression)
        program = Parser(lexer).parse_program()
        env: dict[str, float] = dict(_DEFAULT_ENV)
        fn_env: dict[str, UserFunction] = {}
        last_result: float | None = None
        for stmt in program.body:
            result = execute_statement(stmt, env, fn_env)
            if result is not None:
                last_result = result
    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)

    # 4. Output
    if last_result is not None:
        print(format_result(last_result))


if __name__ == "__main__":
    main()
