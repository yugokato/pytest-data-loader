from io import BufferedReader, TextIOWrapper
from pathlib import Path

import pytest
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize
from tests.tests_loader.helper import PATH_TEXT_FILE, get_parametrized_test_idx

pytestmark = pytest.mark.readers


# NOTE: These tests don't make much sense in reality since open() already handles the same things.
#       These tests just make sures that the file_reader option works as low level


@load(
    ("file_path", "data"),
    PATH_TEXT_FILE,
    file_reader=BufferedReader,
    onload_func=lambda r: TextIOWrapper(r, encoding="utf-8").read(),
    mode="rb",
)
def test_load_text_file_with_reader(file_path: Path, data: str) -> None:
    """Test @load loader with text file reader"""
    assert isinstance(data, str)
    assert data == file_path.read_text()


@parametrize(
    ("file_path", "data"),
    PATH_TEXT_FILE,
    file_reader=BufferedReader,
    onload_func=lambda r: TextIOWrapper(r, encoding="utf-8").read(),
    mode="rb",
)
def test_parametrize_text_file_with_reader(request: FixtureRequest, file_path: Path, data: str) -> None:
    """Test @parametrize loader with text file reader"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == file_path.read_text().splitlines()[idx]
