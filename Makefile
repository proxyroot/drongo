.PHONY: help install lint format type test cov check server build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv, install drongo[dev] editable, set up pre-commit
	uv venv
	uv pip install -e ".[dev]"
	-uv run pre-commit install

lint: ## Lint with ruff
	uv run ruff check .

format: ## Auto-format with ruff
	uv run ruff format .

type: ## Type-check with mypy
	uv run mypy

test: ## Run the test suite
	uv run pytest

cov: ## Run tests with coverage report
	uv run pytest --cov=drongo --cov-report=term-missing

check: ## Run all quality gates (lint + format check + type + test)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run pytest

server: ## Run the standalone mock server
	uv run drongo server

build: ## Build sdist + wheel
	uv build

clean: ## Remove build/test caches
	rm -rf dist build .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
	find . -type d -name '__pycache__' -exec rm -rf {} +
