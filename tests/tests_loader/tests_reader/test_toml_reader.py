import tomllib
from typing import Any

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.paths import PATH_TOML_FILE, PATH_TOML_FILE_DIR

pytestmark = pytest.mark.readers


@load("data", PATH_TOML_FILE, reader=tomllib.load, read_options={"mode": "rb"})
def test_load_toml_file_with_reader(data: dict[str, Any]) -> None:
    """Test @load loader with TOML file reader"""
    assert isinstance(data, dict)


@parametrize("data", PATH_TOML_FILE, reader=tomllib.load, read_options={"mode": "rb"})
def test_parametrize_toml_file_with_reader(data: tuple[str, Any]) -> None:
    """Test @parametrize loader with TOML file reader"""
    assert isinstance(data, tuple)


@parametrize_dir("data", PATH_TOML_FILE_DIR, reader=lambda f: tomllib.load, read_options={"mode": "rb"})
def test_parametrize_dir_with_toml_reader(data: dict[str, Any]) -> None:
    """Test @parametrize_dir loader with TOML file reader"""
    assert isinstance(data, dict)
