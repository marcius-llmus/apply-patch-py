import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless `-m integration` is explicitly selected."""

    # If the user doesn't provide a marker expression, integration tests should
    # be skipped by default.
    if not config.getoption("-m"):
        skip_me = pytest.mark.skip(reason="use `-m integration` to run this test")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_me)
