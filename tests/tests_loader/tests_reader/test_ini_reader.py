from configparser import ConfigParser, SectionProxy
from io import TextIOWrapper
from typing import Any

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import PATH_INI_FILE, PATH_INI_FILE_DIR

pytestmark = pytest.mark.readers

parser = ConfigParser()


def yaml_file_reader(f: TextIOWrapper) -> ConfigParser:
    parser.read_file(f)
    return parser


@load("data", PATH_INI_FILE, file_reader=yaml_file_reader)
def test_load_ini_file_with_reader(data: ConfigParser) -> None:
    """Test @load loader with INI file reader"""
    assert isinstance(data, ConfigParser)
    assert len(data.sections()) > 1


@load(
    "data",
    PATH_INI_FILE,
    file_reader=yaml_file_reader,
    onload_func=lambda parser: {s: dict(parser.items(s)) for s in parser.sections()},
)
def test_load_ini_file_with_reader_and_onload_func(data: dict[str, Any]) -> None:
    """Test @load loader with INI file reader and onload_func"""
    assert isinstance(data, dict)


@parametrize("data", PATH_INI_FILE, file_reader=yaml_file_reader)
def test_parametrize_ini_file_with_reader(data: tuple[str, Any]) -> None:
    """Test @parametrize loader with INI file reader"""
    assert isinstance(data, tuple)
    section_name, section_data = data
    assert isinstance(section_name, str)
    assert isinstance(section_data, SectionProxy)


@parametrize_dir("data", PATH_INI_FILE_DIR, file_reader_func=lambda _: yaml_file_reader)
def test_parametrize_dir_with_init_reader(data: ConfigParser) -> None:
    """Test @parametrize_dir loader with INI file reader"""
    assert isinstance(data, ConfigParser)
    assert len(data.sections()) > 1
