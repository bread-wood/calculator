from __future__ import annotations

import argparse
import sys
from pathlib import Path

from calc.errors import (
    CalcError,
    InvalidDomainBounds,
    OutputWriteError,
    UndefinedFunction,
    UnsupportedFormat,
    UnknownFunction,
    error_message,
    ExpectedSingleArg,
    EmptyExpression,
)
from calc.evaluator import _DEFAULT_ENV, execute_statement, format_result, UserFunction
from calc.lexer import Lexer
from calc.parser import Parser

SUBCOMMANDS: frozenset[str] = frozenset({"plot"})


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SUBCOMMANDS:
        _legacy_eval()
    else:
        parser = _build_parser()
        args = parser.parse_args()
        args.func(args)


def _legacy_eval() -> None:
    """Existing expression pipeline — unchanged from v0.4.x."""
    if len(sys.argv) == 1:
        print("usage: calc '<expression>'", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) != 2:
        print(error_message(ExpectedSingleArg()), file=sys.stderr)
        sys.exit(1)

    expression = sys.argv[1]

    if expression == "":
        print(error_message(EmptyExpression()), file=sys.stderr)
        sys.exit(1)

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

    if last_result is not None:
        print(format_result(last_result))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calc")
    subparsers = parser.add_subparsers(dest="subcommand")

    plot_parser = subparsers.add_parser("plot", help="Plot a function of x")
    plot_parser.add_argument("expression", type=str,
                             help="Expression in x, e.g. 'sin(x)'")
    plot_parser.add_argument("--xmin", type=float, default=-10.0)
    plot_parser.add_argument("--xmax", type=float, default=10.0)
    plot_parser.add_argument("--width", type=int, default=800)
    plot_parser.add_argument("--height", type=int, default=600)
    plot_parser.add_argument("--output", type=Path, default=Path("./plot.png"))
    plot_parser.set_defaults(func=run_plot)

    return parser


def run_plot(args: argparse.Namespace) -> None:
    """Validate args, build scene, render to file. Exits 1 on any error."""
    from calc.plotter import build_scene
    from calc.renderer import get_renderer

    try:
        try:
            # 1. Validate domain bounds
            if args.xmin >= args.xmax:
                raise InvalidDomainBounds()

            # 2. Validate output format
            output = Path(args.output)
            if output.suffix not in {".png", ".svg"}:
                raise UnsupportedFormat(output.suffix)

            # 3. Parse expression
            prog = Parser(Lexer(args.expression)).parse_program()
            ast = prog.body[0]

            # 4. Build scene
            scene = build_scene(ast, args.xmin, args.xmax, args.width, args.height)

            # 5. Render
            renderer = get_renderer(output)
            try:
                renderer.render(scene, output)
            except OSError as e:
                raise OutputWriteError(str(e)) from e

        except UnknownFunction as e:
            raise UndefinedFunction(e.name) from e

    except CalcError as e:
        print(error_message(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
