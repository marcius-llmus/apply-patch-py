.PHONY: init install format lint test build publish publish-test clean

PYTHON ?= uv run

DIST_DIR := dist

init:
	@command -v uv >/dev/null 2>&1 || { echo >&2 "Error: uv is not installed."; exit 1; }
	@command -v python >/dev/null 2>&1 || { echo >&2 "Error: python is not installed."; exit 1; }

install: init
	@uv sync

format: init
	@$(PYTHON) ruff check . --fix
	@$(PYTHON) black .

lint: init
	@$(PYTHON) ruff check .
	@$(PYTHON) black --check .
	@$(PYTHON) mypy src

test: init
	@$(PYTHON) pytest

# Preferred build (uv)
build: init
	@rm -rf $(DIST_DIR)
	@uv build
	@ls -la $(DIST_DIR)

# Publish to PyPI (requires UV_PUBLISH_TOKEN)
publish: init
	@test -n "$$UV_PUBLISH_TOKEN" || { echo >&2 "Error: UV_PUBLISH_TOKEN is not set"; exit 1; }
	@uv publish

# Publish to TestPyPI (requires UV_PUBLISH_TOKEN)
publish-test: init
	@test -n "$$UV_PUBLISH_TOKEN" || { echo >&2 "Error: UV_PUBLISH_TOKEN is not set"; exit 1; }
	@UV_PUBLISH_URL=https://test.pypi.org/legacy/ uv publish

clean:
	@rm -rf $(DIST_DIR) .pytest_cache .ruff_cache .mypy_cache
