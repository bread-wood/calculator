import sys

from calc.errors import CalcError, ExpectedSingleArg, EmptyExpression, error_message
from calc.lexer import Lexer
from calc.parser import Parser
from calc.evaluator import evaluate, format_result


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
        ast = Parser(lexer).parse_program().body[0]
        result = evaluate(ast)
    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)

    # 4. Output
    print(format_result(result))


if __name__ == "__main__":
    main()
