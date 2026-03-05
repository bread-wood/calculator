# calc

A command-line arithmetic expression evaluator that parses and computes infix expressions with support for standard operators and parentheses.

## Usage

```bash
# Install
uv sync

# Evaluate an expression
uv run calc "2 + 3 * (4 - 1)"
# Output: 11
```

## Development

```bash
make test   # run tests
make lint   # run linter
```
