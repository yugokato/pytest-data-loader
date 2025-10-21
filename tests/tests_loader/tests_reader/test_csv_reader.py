import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import (
    PATH_CSV_FILE,
    PATH_CSV_FILE_DIR,
    PATH_CSV_FILE_SEMICOLON,
    get_parametrized_test_idx,
)

pytestmark = pytest.mark.readers

read_options = dict(encoding="utf-8-sig", newline="")
DELIMITER = {"comma": ",", "semicolon": ","}


@load(("file_path", "data"), PATH_CSV_FILE, file_reader=csv.reader, **read_options)
def test_load_csv_file_with_reader(file_path: Path, data: Iterator[list[str]]) -> None:
    """Test @load loader with CSV file reader"""
    assert isinstance(data, Iterator)
    expected_data = get_expected_data(file_path, read_options)
    rows: list[list[str]] = []
    for i, row in enumerate(data):
        assert isinstance(row, list)
        assert DELIMITER[file_path.stem].join(row) == expected_data[i]
        rows.append(row)
    assert len(rows) == len(expected_data)


@load(
    ("file_path", "data"),
    PATH_CSV_FILE_SEMICOLON,
    file_reader=lambda f: csv.reader(f, delimiter=DELIMITER[PATH_CSV_FILE_SEMICOLON.stem]),
    **read_options,
)
def test_load_csv_file_with_reader_options(file_path: Path, data: Iterator[list[str]]) -> None:
    """Test @load loader with CSV file reader and reader options"""
    assert isinstance(data, Iterator)
    expected_data = get_expected_data(file_path, read_options)
    rows: list[list[str]] = []
    for i, row in enumerate(data):
        assert isinstance(row, list)
        assert DELIMITER[file_path.stem].join(row) == expected_data[i]
        rows.append(row)
    assert len(rows) == len(expected_data)


@load(("file_path", "data"), PATH_CSV_FILE, file_reader=csv.DictReader, **read_options)
def test_load_csv_file_with_dict_reader(file_path: Path, data: Iterator[dict[str, str]]) -> None:
    """Test @load loader with CSV DictReader reader"""
    assert isinstance(data, Iterator)
    expected_data = get_expected_data(file_path, read_options)
    rows: list[dict[str, str]] = []
    for i, row in enumerate(data):
        assert isinstance(row, dict)
        assert DELIMITER[file_path.stem].join(row.keys()) == expected_data[0]
        assert DELIMITER[file_path.stem].join(row.values()) == expected_data[i + 1]
        rows.append(row)
    assert len(rows) == len(expected_data) - 1


@parametrize(("file_path", "data"), PATH_CSV_FILE, file_reader=csv.reader, **read_options)
def test_parametrize_csv_file_with_reader(request: FixtureRequest, file_path: Path, data: list[str]) -> None:
    """Test @parametrize loader with CSV file reader"""
    assert isinstance(data, list)
    expected_data = get_expected_data(file_path, read_options)
    idx = get_parametrized_test_idx(request, arg_name="data")
    assert DELIMITER[file_path.stem].join(data) == expected_data[idx]


@parametrize(("file_path", "data"), PATH_CSV_FILE, file_reader=csv.DictReader, **read_options)
def test_parametrize_csv_file_with_dict_reader(request: FixtureRequest, file_path: Path, data: Any) -> None:
    """Test @parametrize loader with CSV DictReader reader"""
    assert isinstance(data, dict)
    expected_data = get_expected_data(file_path, read_options)
    idx = get_parametrized_test_idx(request, arg_name="data")
    assert DELIMITER[file_path.stem].join(data.keys()) == expected_data[0]
    assert DELIMITER[file_path.stem].join(data.values()) == expected_data[idx + 1]


@parametrize_dir(
    ("file_path", "data"),
    PATH_CSV_FILE_DIR,
    file_reader_func=lambda p: (lambda f: csv.reader(f, delimiter=DELIMITER[p.stem])),
    read_option_func=lambda f: read_options,
)
def test_parametrize_dir_with_csv_reader(file_path: Path, data: Iterator[list[str]]) -> None:
    """Test @parametrize_dir loader with CSV file reader"""
    assert isinstance(data, Iterator)
    expected_data = get_expected_data(file_path, read_options)
    rows: list[list[str]] = []
    for i, row in enumerate(data):
        assert DELIMITER[file_path.stem].join(row) == expected_data[i]
        rows.append(row)
    assert len(rows) == len(expected_data)


def get_expected_data(file_path: Path, read_options: dict[str, Any]) -> list[str]:
    with open(file_path, **read_options) as f:
        return f.read().splitlines()
