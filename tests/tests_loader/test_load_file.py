import json
from typing import Any

import pytest
from pytest import FixtureRequest

from pytest_data_loader import load
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_JPEG_FILE,
    PATH_JSON_FILE_NESTED_OBJECT,
    PATH_JSON_FILE_OBJECT,
    PATH_TEXT_FILE,
)

pytestmark = pytest.mark.loaders

# NOTE:
# - lazy_loading option is separately tested in another test using pytester
# - This file covers 3 types of data types the plugin handles differently: text file, json file, and binary file


# Text file
@load("data", PATH_TEXT_FILE)
def test_load_text_file_with_no_options(data: str) -> None:
    """Test @load loader with no options using text file"""
    assert isinstance(data, str)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()


@load("data", PATH_TEXT_FILE, mode="rb")
def test_load_text_file_in_binary_mode(data: bytes) -> None:
    """Test @load loader in binary mode using text file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_bytes()


@load("data", PATH_TEXT_FILE, onload_func=lambda d: "# foo\n" + d)
def test_load_text_file_with_onload_func(data: str) -> None:
    """Test @load loader with the onload_func option using text file"""
    assert isinstance(data, str)
    assert data == "# foo\n" + (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).read_text()


@load("data", PATH_TEXT_FILE, id="foo")
def test_load_text_file_with_id(request: FixtureRequest, data: str) -> None:
    """Test @load loader with the id option using text file"""
    assert request.node.name.endswith("[foo]")


# JSON file
@load("data", PATH_JSON_FILE_OBJECT)
def test_load_json_file_with_no_options(data: dict[str, Any]) -> None:
    """Test @load loder with no options using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_text())


@load("data", PATH_JSON_FILE_OBJECT, mode="rb")
def test_load_json_file_with_force_binary(data: dict[str, Any]) -> None:
    """Test @load loder in binary mode using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).read_bytes())


@load("data", PATH_JSON_FILE_NESTED_OBJECT, onload_func=lambda d: d["dev"])
def test_load_json_file_with_onload_func(data: dict[str, Any]) -> None:
    """Test @load loder with the onload_func option using JSON file"""
    assert isinstance(data, dict)
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_NESTED_OBJECT).read_bytes())["dev"]


@load("data", PATH_JSON_FILE_OBJECT, id="foo")
def test_load_json_file_with_id(request: FixtureRequest, data: dict[str, Any]) -> None:
    """Test @load loder with the id option using JSON file"""
    assert request.node.name.endswith("[foo]")


# Binary file
@load("data", PATH_JPEG_FILE)
def test_load_binary_file_with_no_options(data: bytes) -> None:
    """Test @load loder with no options using binary file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, mode="rb")
def test_load_binary_file_with_force_binary(data: bytes) -> None:
    """Test @load loder in binary mode using binary file"""
    assert isinstance(data, bytes)
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, onload_func=lambda d: b"# foo" + d)
def test_load_binary_file_with_onload_func(data: bytes) -> None:
    """Test @load loder with the onload_func option using binary file"""
    assert isinstance(data, bytes)
    assert data == b"# foo" + (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()


@load("data", PATH_JPEG_FILE, id="foo")
def test_load_binary_file_with_id(request: FixtureRequest, data: bytes) -> None:
    """Test @load loder with the id option using binary file"""
    assert request.node.name.endswith("[foo]")
