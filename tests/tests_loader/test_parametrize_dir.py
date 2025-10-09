from pathlib import Path

from pytest import FixtureRequest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.types import LoadedDataType
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_IMAGE_DIR,
    PATH_SOME_DIR,
    get_parametrized_test_idx,
)

# NOTE:
# - lazy_loading option is separately tested in another test using pytester
# - This file covers 3 types of data types the plugin handles differently: text file, json file, and binary file


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


@parametrize_dir(("file_path", "data"), PATH_SOME_DIR, force_binary=True)
def test_parametrize_dir_with_force_binary(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loder with the force_binary option"""
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
