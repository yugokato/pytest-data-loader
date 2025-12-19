from pathlib import Path

import pandas
import pytest
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import PATH_CSV_FILE, PATH_CSV_FILE_DIR, get_parametrized_test_idx

pytestmark = pytest.mark.readers


DELIMITER = {"comma": ",", "semicolon": ","}


@load(("file_path", "df"), PATH_CSV_FILE, file_reader=pandas.read_csv)
def test_load_csv_file_with_pandas(file_path: Path, df: pandas.DataFrame) -> None:
    """Test @load loader with the CSV reader from pandas"""
    assert isinstance(df, pandas.DataFrame)
    expected_data = get_expected_data(file_path)
    for i, row in df.iterrows():
        assert isinstance(row, pandas.Series)
        assert DELIMITER[file_path.stem].join(row.to_list()) == expected_data[i + 1]


@parametrize(
    ("file_path", "idx_and_row"), PATH_CSV_FILE, file_reader=pandas.read_csv, parametrizer_func=lambda df: df.iterrows()
)
def test_parametrize_csv_file_with_pandas(
    request: FixtureRequest, file_path: Path, idx_and_row: tuple[int, pandas.Series]
) -> None:
    """Test @parametrize loader with the CSV reader from pands"""
    assert isinstance(idx_and_row, tuple)
    i, row = idx_and_row
    expected_data = get_expected_data(file_path)
    assert i == get_parametrized_test_idx(request, arg_name="idx_and_row")
    assert DELIMITER[file_path.stem].join(row.to_list()) == expected_data[i + 1]


@parametrize_dir(
    ("file_path", "df"),
    PATH_CSV_FILE_DIR,
    file_reader_func=lambda p: (lambda f: pandas.read_csv(f, delimiter=DELIMITER[p.stem])),
)
def test_parametrize_dir_with_pandas(file_path: Path, df: pandas.DataFrame) -> None:
    """Test @parametrize_dir loader with the CSV reader from pands"""
    assert isinstance(df, pandas.DataFrame)
    expected_data = get_expected_data(file_path)
    rows: list[pandas.Series] = []
    for i, row in df.iterrows():
        assert DELIMITER[file_path.stem].join(row.to_list()) == expected_data[i + 1]
        rows.append(row)
    assert len(rows) + 1 == len(expected_data)


def get_expected_data(file_path: Path) -> list[str]:
    with open(file_path) as f:
        return f.read().splitlines()
