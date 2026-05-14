import json
from pathlib import Path
from typing import Any

import pytest
from pytest import FixtureRequest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.paths import get_effective_suffix
from pytest_data_loader.types import LoadedDataType
from tests.paths import (
    ABS_PATH_LOADER_DIR,
    IMAGE_DIR,
    PATH_COMPRESSED_FILE_DIR,
    PATH_JPEG_FILE,
    PATH_JSON_FILE_OBJECT,
    PATH_TEXT_FILE,
    PATH_TEXT_FILE_DIR,
    PATH_YAML_FILE,
    SOME_DIR,
    SOME_DIR_INNER,
)

from .helper import get_parametrized_test_idx

pytestmark = pytest.mark.loaders

# NOTE:
# - lazy_loading option is separately tested in another test using pytester


@parametrize_dir(("file_path", "data"), SOME_DIR)
def test_parametrize_dir_with_no_options(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with no options using text files"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert file_path == ABS_PATH_LOADER_DIR / SOME_DIR / f"{idx}.txt"
    assert data == f"data{idx}"


@parametrize_dir(("file_path", "data"), IMAGE_DIR)
def test_parametrize_dir_with_no_options_binary(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with no options using binary files"""
    assert isinstance(data, bytes)
    assert data == file_path.read_bytes()


@parametrize_dir(("file_path", "data"), SOME_DIR, read_options=lambda x: {"mode": "rb"})
def test_parametrize_dir_in_binary_mode(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader in binary mode"""
    assert isinstance(data, bytes)
    assert data == file_path.read_bytes()


@parametrize_dir(("file_path", "data"), SOME_DIR, filter=lambda x: int(x.stem) % 2 == 1)
def test_parametrize_dir_with_filter(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the filter option"""
    assert int(file_path.stem) % 2 == 1


@parametrize_dir(("file_path", "data"), SOME_DIR, processor=lambda x: "# " + x)
def test_parametrize_dir_with_processor(file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the processor option"""
    assert data == "# " + file_path.read_text()


@parametrize_dir(("file_path", "data"), IMAGE_DIR, marks=lambda x: getattr(pytest.mark, x.suffix[1:]))
def test_parametrize_dir_with_marks_callable(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the marks option (callable)"""
    assert request.node.get_closest_marker(file_path.suffix[1:])


@parametrize_dir(("file_path", "data"), SOME_DIR, marks=pytest.mark.foo)
def test_parametrize_dir_with_marks_single(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the marks option (single mark applied to all)"""
    assert request.node.get_closest_marker("foo")


@parametrize_dir(("file_path", "data"), SOME_DIR, marks=[pytest.mark.foo, pytest.mark.bar])
def test_parametrize_dir_with_marks_multi(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the marks option (a collection of marks applied to all)"""
    mark_names = {m.name for m in request.node.own_markers}
    assert "foo" in mark_names
    assert "bar" in mark_names


@parametrize_dir(("file_path", "data"), SOME_DIR, ids=lambda x: x.stem)
def test_parametrize_dir_with_ids_callable(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the ids option (callable)"""
    assert request.node.nodeid.endswith(f"[{file_path.stem}]")


@parametrize_dir(("file_path", "data"), SOME_DIR, ids=["a", "b", "c"])
def test_parametrize_dir_with_ids_sequence(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with the ids option (a sequence of IDs)"""
    idx = get_parametrized_test_idx(request, "data")
    expected_ids = ["a", "b", "c"]
    assert request.node.nodeid.endswith(f"[{expected_ids[idx]}]")


@parametrize_dir(("file_path", "data"), SOME_DIR, recursive=True)
def test_parametrize_dir_recursive(request: FixtureRequest, file_path: Path, data: LoadedDataType) -> None:
    """Test @parametrize_dir loader with recursive option"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    if file_path.parent == ABS_PATH_LOADER_DIR / SOME_DIR:
        assert file_path == ABS_PATH_LOADER_DIR / SOME_DIR / f"{idx}.txt"
    else:
        assert file_path == ABS_PATH_LOADER_DIR / SOME_DIR / SOME_DIR_INNER / f"{idx}.txt"
    assert data == f"data{idx}"


@parametrize_dir(("file_path", "_"), SOME_DIR, recursive=True, filter=lambda x: int(x.stem) % 2 == 1)
def test_parametrize_dir_recursive_and_filter(file_path: Path, _: LoadedDataType) -> None:
    """Test @parametrize_dir loader with recursive and filter option"""
    assert int(file_path.stem) % 2 == 1


@parametrize_dir("data", [SOME_DIR, PATH_TEXT_FILE_DIR])
def test_parametrize_dir_multi_dirs(request: FixtureRequest, data: str) -> None:
    """Test @parametrize_dir loader with a list of dir paths concatenates all parametrized data"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    all_expected = ["data0", "data1", "data2", "line0\nline1\nline2"]
    assert data == all_expected[idx]


@parametrize_dir("data", [SOME_DIR, PATH_TEXT_FILE_DIR], recursive=True)
def test_parametrize_dir_multi_dirs_recursive(request: FixtureRequest, data: str) -> None:
    """Test @parametrize_dir loader with recursive option with a list of dir paths concatenates all parametrized data"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    all_expected = ["data0", "data1", "data2", "data3", "data4", "data5", "line0\nline1\nline2"]
    assert data == all_expected[idx]


@parametrize_dir(
    ("file_path", "data"),
    PATH_COMPRESSED_FILE_DIR,
    filter=lambda p: get_effective_suffix(p) in (".txt", ".json", ".yml", ".jpg"),
)
def test_parametrize_dir_with_compressed_files(file_path: Path, data: Any) -> None:
    """Test @parametrize_dir loader with compressed files in the directory"""
    effective_suffix = get_effective_suffix(file_path)
    if effective_suffix == ".txt":
        assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()
    elif effective_suffix == ".json":
        assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_text())
    elif effective_suffix == ".yml":
        assert data == (ABS_PATH_LOADER_DIR / PATH_YAML_FILE).read_text()
    elif effective_suffix == ".jpg":
        assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()
    else:
        raise NotImplementedError("Add test")
