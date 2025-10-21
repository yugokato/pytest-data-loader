from pathlib import Path

import pytest
from pytest import FixtureRequest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.types import LoadedDataType
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR, PATH_IMAGE_DIR, PATH_SOME_DIR, get_parametrized_test_idx

pytestmark = pytest.mark.loaders

# NOTE:
# - lazy_loading option is separately tested in another test using pytester


@parametrize_dir(("file_path", "data"), PATH_SOME_DIR)
def test_parametrize_dir_with_no_options(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with no options using text files"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert file_path == ABS_PATH_LOADER_DIR / PATH_SOME_DIR / f"{idx}.txt"
    assert data == f"data{idx}"


@parametrize_dir(("file_path", "data"), PATH_IMAGE_DIR)
def test_parametrize_dir_with_no_options_binary(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with no options using binary files"""
    assert isinstance(data, bytes)
    assert data == file_path.read_bytes()


@parametrize_dir(("file_path", "data"), PATH_SOME_DIR, read_option_func=lambda x: {"mode": "rb"})
def test_parametrize_dir_in_binary_mode(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder in binary mode"""
    assert isinstance(data, bytes)
    assert data == file_path.read_bytes()


@parametrize_dir(("file_path", "data"), PATH_SOME_DIR, filter_func=lambda x: int(x.stem) % 2 == 1)
def test_parametrize_dir_with_filter_func(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with the filter_func option"""
    assert int(file_path.stem) % 2 == 1


@parametrize_dir(("file_path", "data"), PATH_SOME_DIR, process_func=lambda x: "# " + x)
def test_parametrize_dir_with_process_func(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with the process_func option"""
    assert data == "# " + file_path.read_text()


@parametrize_dir(
    ("file_path", "data"),
    PATH_IMAGE_DIR,
    marker_func=lambda x: getattr(pytest.mark, x.suffix[1:]),
)
def test_parametrize_dir_with_marker_func(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with the marker_func option"""
    marker = request.node.get_closest_marker(file_path.suffix[1:])
    assert marker
