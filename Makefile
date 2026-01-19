.PHONY: init install format lint test build publish publish-test verify-testpypi clean

PYTHON ?= uv run

DIST_DIR := dist

init:
	@command -v uv >/dev/null 2>&1 || { echo >&2 "Error: uv is not installed."; exit 1; }
	@command -v python >/dev/null 2>&1 || { echo >&2 "Error: python is not installed."; exit 1; }

install: init
	@uv sync

format: init
	@$(PYTHON) ruff check src tests --fix
	@$(PYTHON) black src tests

lint: init
	@$(PYTHON) ruff check src tests
	@$(PYTHON) black --check src tests
	@$(PYTHON) mypy src

test: init
	@$(PYTHON) pytest

test-integration: init
	@$(PYTHON) pytest -m integration

# Preferred build (uv)
build: init
	@rm -rf $(DIST_DIR)
	@uv build
	@ls -la $(DIST_DIR)

# Publish to PyPI (requires UV_PUBLISH_TOKEN)
publish: build
	@test -n "$$UV_PUBLISH_TOKEN" || { echo >&2 "Error: UV_PUBLISH_TOKEN is not set"; exit 1; }
	@uv publish

clean:
	@rm -rf $(DIST_DIR) .pytest_cache .ruff_cache .mypy_cache
