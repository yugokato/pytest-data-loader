from pathlib import Path
from typing import Any

import pytest

from pytest_data_loader import load
from pytest_data_loader.constants import PYTEST_DATA_LOADER_ATTR
from pytest_data_loader.types import DataLoaderLoadAttrs

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("fixture_names", ["data", "file_path, data", ("file_path", "data")])
def test_data_loader_setup(fixture_names: Any) -> None:
    """Test data loader setup on a test function"""
    relative_path = "fake.txt"

    @load(fixture_names, relative_path)
    def test_something(*args: Any) -> None: ...

    assert hasattr(test_something, PYTEST_DATA_LOADER_ATTR)
    load_attr = getattr(test_something, PYTEST_DATA_LOADER_ATTR)
    assert isinstance(load_attr, DataLoaderLoadAttrs)
    if isinstance(fixture_names, str):
        fixtures = tuple(x.strip() for x in fixture_names.split(","))
    else:
        fixtures = fixture_names
    assert load_attr.loader is load
    assert load_attr.fixture_names == fixtures
    assert load_attr.relative_path == Path(relative_path)
    assert load_attr.requires_file_path == (len(fixtures) == 2)
