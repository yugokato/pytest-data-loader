import json
from typing import Any

import pytest
from pytest import FixtureRequest

from pytest_data_loader import load
from tests.paths import (
    ABS_PATH_LOADER_DIR,
    PATH_JPEG_FILE,
    PATH_JPEG_FILE_GZ,
    PATH_JSON_FILE_GZ,
    PATH_JSON_FILE_NESTED_OBJECT,
    PATH_JSON_FILE_OBJECT,
    PATH_TEXT_FILE,
    PATH_TEXT_FILE_GZ,
)

pytestmark = pytest.mark.loaders

# NOTE:
# - lazy_loading option is separately tested in another test using pytester
# - This file covers 4 types of data types the plugin handles differently:
#   - text file (no file reader)
#   - json file (with default file reader)
#   - binary file
#   - compressed files (gz, .bz2, .xz) for the above


# Text file
@load("data", PATH_TEXT_FILE)
def test_load_text_file_with_no_options(data: str) -> None:
    """Test @load loader with no options using text file"""
    assert isinstance(data, str)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()


@load("data", PATH_TEXT_FILE, read_options={"mode": "rb"})
def test_load_text_file_in_binary_mode(data: bytes) -> None:
    """Test @load loader in binary mode using text file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_bytes()


@load("data", PATH_TEXT_FILE, onload=lambda d: "# foo\n" + d)
def test_load_text_file_with_onload_func(data: str) -> None:
    """Test @load loader with the onload option using text file"""
    assert isinstance(data, str)
    assert data == "# foo\n" + (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()


@load("data", PATH_TEXT_FILE, id="foo")
def test_load_text_file_with_id(request: FixtureRequest, data: str) -> None:
    """Test @load loader with the id option using text file"""
    assert request.node.name.endswith("[foo]")


@load("data", PATH_TEXT_FILE, marks=pytest.mark.foo)
def test_load_text_file_with_marks(request: FixtureRequest, data: str) -> None:
    """Test @load loader with the marks option using text file"""
    assert "foo" in {m.name for m in request.node.own_markers}


@load("data", PATH_TEXT_FILE, id="foo", marks=pytest.mark.bar)
def test_load_text_file_with_id_and_marks(request: FixtureRequest, data: str) -> None:
    """Test that @load loader supports id and marks together"""
    assert request.node.name.endswith("[foo]")
    assert "bar" in {m.name for m in request.node.own_markers}


# JSON file
@load("data", PATH_JSON_FILE_OBJECT)
def test_load_json_file_with_no_options(data: dict[str, Any]) -> None:
    """Test @load loader with no options using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_text())


@load("data", PATH_JSON_FILE_OBJECT, read_options={"mode": "rb"})
def test_load_json_file_with_force_binary(data: dict[str, Any]) -> None:
    """Test @load loader in binary mode using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_bytes())


@load("data", PATH_JSON_FILE_NESTED_OBJECT, onload=lambda d: d["dev"])
def test_load_json_file_with_onload_func(data: dict[str, Any]) -> None:
    """Test @load loader with the onload option using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_NESTED_OBJECT).read_text())["dev"]


@load("data", PATH_JSON_FILE_OBJECT, id="foo")
def test_load_json_file_with_id(request: FixtureRequest, data: dict[str, Any]) -> None:
    """Test @load loader with the id option using JSON file"""
    assert request.node.name.endswith("[foo]")


@load("data", PATH_JSON_FILE_OBJECT, marks=[pytest.mark.foo, pytest.mark.bar])
def test_load_json_file_with_marks_collection(request: FixtureRequest, data: dict[str, Any]) -> None:
    """Test @load loader with a collection of marks using JSON file"""
    mark_names = {m.name for m in request.node.own_markers}
    assert "foo" in mark_names
    assert "bar" in mark_names


# Binary file
@load("data", PATH_JPEG_FILE)
def test_load_binary_file_with_no_options(data: bytes) -> None:
    """Test @load loader with no options using binary file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, read_options={"mode": "rb"})
def test_load_binary_file_with_force_binary(data: bytes) -> None:
    """Test @load loader in binary mode using binary file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, onload=lambda d: b"# foo" + d)
def test_load_binary_file_with_onload_func(data: bytes) -> None:
    """Test @load loader with the onload option using binary file"""
    assert isinstance(data, bytes)
    assert data == b"# foo" + (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, id="foo")
def test_load_binary_file_with_id(request: FixtureRequest, data: bytes) -> None:
    """Test @load loader with the id option using binary file"""
    assert request.node.name.endswith("[foo]")


@load("data", PATH_JPEG_FILE, marks=pytest.mark.foo)
def test_load_binary_file_with_marks(request: FixtureRequest, data: bytes) -> None:
    """Test @load loader with the marks option using binary file"""
    assert "foo" in {m.name for m in request.node.own_markers}


# Compressed files
@load("data", PATH_TEXT_FILE_GZ)
def test_load_compressed_text_file(data: str) -> None:
    """Test that @load with a .txt.gz file returns decompressed file data"""
    assert isinstance(data, str)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()


@load("data", PATH_JSON_FILE_GZ)
def test_load_compressed_json_file(data: dict[str, Any]) -> None:
    """Test that @load with a .json.gz file resolves to the default json.load reader transparently"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_text())


@load("data", PATH_JPEG_FILE_GZ)
def test_load_compressed_autodetects_binary_mode(data: bytes) -> None:
    """Test that @load with a .jpg.gz file auto-detects binary mode from decompressed content"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_TEXT_FILE_GZ, read_options={"mode": "rb"})
def test_load_compressed_text_with_force_binary(data: bytes) -> None:
    """Test that @load with a .txt.gz file in binary mode returns decompressed bytes"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_bytes()
