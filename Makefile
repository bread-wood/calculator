.PHONY: all build test lint clean install

all: build

build:
	uv sync --frozen
	@echo "Build complete."

test: build
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/

clean:
	rm -rf .venv __pycache__ src/calc/__pycache__ tests/__pycache__ \
	       .pytest_cache dist *.egg-info

install: build
	install -m 755 bin/calc /usr/local/bin/calc
	@echo "Installed to /usr/local/bin/calc"
