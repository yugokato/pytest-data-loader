import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.paths import PATH_JSONL_FILE, PATH_JSONL_FILE_DIR

from ..helper import get_parametrized_test_idx

pytestmark = pytest.mark.readers


def get_expected_data(file_path: Path) -> list[dict[str, Any]]:
    """Read expected data from JSONL file, one dict per non-empty line"""
    with open(file_path) as f:
        return [json.loads(line) for line in f if line.strip()]


@load(("file_path", "data"), PATH_JSONL_FILE)
def test_load_jsonl_file(file_path: Path, data: Iterator[dict[str, Any]]) -> None:
    """Test @load loader with default JSONL reader returns an Iterator of dicts"""
    assert isinstance(data, Iterator)
    expected = get_expected_data(file_path)
    rows = list(data)
    assert len(rows) == len(expected)
    for row, exp in zip(rows, expected):
        assert isinstance(row, dict)
        assert row == exp


@parametrize(("file_path", "data"), PATH_JSONL_FILE)
def test_parametrize_jsonl_file(request: FixtureRequest, file_path: Path, data: dict[str, Any]) -> None:
    """Test @parametrize loader with default JSONL reader, each dict is a separate test case"""
    assert isinstance(data, dict)
    expected = get_expected_data(file_path)
    idx = get_parametrized_test_idx(request, arg_name="data")
    assert data == expected[idx]


@parametrize_dir(("file_path", "data"), PATH_JSONL_FILE_DIR)
def test_parametrize_dir_jsonl(file_path: Path, data: Iterator[dict[str, Any]]) -> None:
    """Test @parametrize_dir loader over a directory of JSONL files"""
    assert isinstance(data, Iterator)
    expected = get_expected_data(file_path)
    rows = list(data)
    assert len(rows) == len(expected)
    for row, exp in zip(rows, expected):
        assert isinstance(row, dict)
        assert row == exp
