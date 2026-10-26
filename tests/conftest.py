"""Keep repository-only corpora out of the default source-distribution suite."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--run-research", action="store_true", default=False,
                     help="Run tests requiring separately licensed repository data")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-research"):
        skip = pytest.mark.skip(reason="repository corpus test; opt in with --run-research")
        for item in items:
            if "research" in item.keywords:
                item.add_marker(skip)
