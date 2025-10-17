from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import PATH_YAML_DOCUMENTS_FILE, PATH_YAML_FILE, PATH_YAML_FILE_DIR

pytestmark = pytest.mark.readers


@load("data", PATH_YAML_FILE, file_reader=yaml.safe_load)
def test_load_yaml_file_with_reader(data: dict[str, Any]) -> None:
    """Test @load loader with YAML file reader"""
    assert isinstance(data, dict)


@load(("file_path", "data"), PATH_YAML_DOCUMENTS_FILE, file_reader=yaml.safe_load_all)
def test_load_yaml_documents_file_with_reader(file_path: Path, data: Iterator[dict[str, Any]]) -> None:
    """Test @load loader with YAML documents file reader"""
    assert isinstance(data, Iterator)
    expected_documents = list(yaml.safe_load_all(file_path.read_text()))
    documents = []
    for i, document in enumerate(data):
        assert isinstance(document, dict)
        assert document == expected_documents[i]
        documents.append(document)
    assert len(documents) == len(expected_documents)


@parametrize("data", PATH_YAML_FILE, file_reader=yaml.safe_load)
def test_parametrize_yaml_file_with_reader(data: tuple[str, Any]) -> None:
    """Test @parametrize loader with YAML file reader"""
    assert isinstance(data, tuple)


@parametrize("data", PATH_YAML_DOCUMENTS_FILE, file_reader=yaml.safe_load_all)
def test_parametrize_yaml_documents_file_with_reader(data: dict[str, Any]) -> None:
    """Test @parametrize loader with YAML documents file reader"""
    assert isinstance(data, dict)


@parametrize_dir(
    ("file_path", "data"),
    PATH_YAML_FILE_DIR,
    file_reader_func=lambda f: yaml.safe_load if "documents" not in f.name else yaml.safe_load_all,
)
def test_parametrize_dir_with_yaml_reader(file_path: Path, data: dict[str, Any] | Iterator[dict[str, Any]]) -> None:
    """Test @parametrize_dir loader with YAML file reader"""
    if "documents" in file_path.name:
        assert isinstance(data, Iterator)
        assert len(list(data)) == len(list(yaml.safe_load_all(file_path.read_text())))
    else:
        assert isinstance(data, dict)
