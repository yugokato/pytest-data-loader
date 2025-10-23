from pathlib import Path
from typing import Any

import pytest
from pytest import ExitCode, Pytester

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("register", [False, True])
def test_file_reader_registration(pytester: Pytester, register: bool, override: bool) -> None:
    """Test file reader registration and per-test overriding"""
    rel_path, file_data = _setup_data(pytester)
    if register or override:
        _create_conftest_with_reader_registration(
            pytester, "csv.reader", read_options={"encoding": "utf-8-sig", "newline": ""}
        )
    if override:
        reader_def = ", file_reader=csv.DictReader"
    else:
        reader_def = ""
    pytester.makepyfile(f"""
    import csv
    from collections.abc import Iterator
    from pathlib import Path

    import pytest_data_loader
    from pytest_data_loader.loaders.reader import FileReader

    register = {register}
    override = {override}

    @pytest_data_loader.load("data", {rel_path!r}{reader_def})
    def test_something(data):
        if register or override:
            file_reader = FileReader.get_registered_reader(Path(__file__), ".csv")
            assert file_reader is not None
            assert isinstance(data, Iterator)
            assert file_reader.reader == csv.reader
            if override:
                # csv.DictReader should be applied
                assert isinstance(next(data), dict)
            else:
                # csv.reader should be applied
                assert isinstance(next(data), list)
        else:
            assert isinstance(data, str)
            assert data == {file_data!r}
    """)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1)


def test_file_reader_registration_in_multiple_conftest(pytester: Pytester) -> None:
    """Test that reader registration in the nearest conftest.py should be effective"""
    orig_dir = pytester.path
    rel_path, _ = _setup_data(pytester)

    # Register reader in the top-level confest.py
    _create_conftest_with_reader_registration(
        pytester, "csv.reader", read_options={"encoding": "utf-8-sig", "newline": ""}
    )

    # Create a child dir with empty conftest.py in it
    p = pytester.mkdir("tests_something")
    pytester._path = p
    pytester.chdir()
    pytester.makeconftest("")

    # Create another child dir and register reader in confest.py
    p = pytester.mkdir("tests_something2")
    pytester._path = p
    pytester.chdir()
    _create_conftest_with_reader_registration(
        pytester, "csv.DictReader", read_options={"encoding": "utf-8-sig", "newline": ""}
    )

    # Create test file
    pytester.makepyfile(f"""
       import csv
       from collections.abc import Iterator
       from pathlib import Path

       import pytest_data_loader
       from pytest_data_loader.loaders.reader import FileReader

       @pytest_data_loader.load("data", {rel_path!r})
       def test_something(data):
           file_reader = FileReader.get_registered_reader(Path(__file__), ".csv")
           assert file_reader is not None
           assert file_reader.reader == csv.DictReader
           assert isinstance(data, Iterator)
           assert isinstance(next(data), dict)
       """)

    pytester._path = orig_dir
    pytester.chdir()

    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1)


def test_file_reader_registration_with_invalid_reader(pytester: Pytester) -> None:
    """Test that file reader is validated during registration"""
    rel_path, _ = _setup_data(pytester)
    _create_conftest_with_reader_registration(pytester, '"foo"')
    _create_pyfile_for_negative_cases(pytester, rel_path)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.USAGE_ERROR
    assert "file_reader: Expected an iterable or a callable" in str(result.stderr)


def test_file_reader_registration_with_invalid_read_options(pytester: Pytester) -> None:
    """Test that file read option is validated during registration"""
    rel_path, _ = _setup_data(pytester)
    _create_conftest_with_reader_registration(pytester, "csv.reader", read_options={"mode": "w"})
    _create_pyfile_for_negative_cases(pytester, rel_path)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.USAGE_ERROR
    assert "read_options: Invalid read mode" in str(result.stderr)


def test_file_reader_registration_in_non_conftest(pytester: Pytester) -> None:
    """Test that reader registration is not allowed outside conftest.py"""
    rel_path, _ = _setup_data(pytester)
    _create_pyfile_for_negative_cases(
        pytester, rel_path, registration='pytest_data_loader.register_reader(".csv", csv.reader)'
    )
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    assert "must be called from a conftest.py" in str(result.stdout)


def _setup_data(pytester: Pytester) -> tuple[str, str]:
    pytester.mkdir(DEFAULT_LOADER_DIR_NAME)
    rel_path = "test.csv"
    file_data = "H1,H2,H3\nC1-1,C1-2,C1-3\nC2-1,C2-2,C2-3"
    pytester.makefile(".csv", **{str(Path(DEFAULT_LOADER_DIR_NAME, rel_path)): file_data})
    return rel_path, file_data


def _create_conftest_with_reader_registration(
    pytester: Pytester, reader_def: str, read_options: dict[str, Any] | None = None
) -> None:
    if read_options:
        read_option_def = ", ".join(f"{k}={v!r}" for k, v in read_options.items())
    else:
        read_option_def = ""
    pytester.makeconftest(f"""
    import csv
    import pytest_data_loader

    pytest_data_loader.register_reader(".csv", {reader_def}, {read_option_def})
    """)


def _create_pyfile_for_negative_cases(pytester: Pytester, rel_path: str, registration: str = "") -> Path:
    return pytester.makepyfile(f"""
    import csv
    import pytest_data_loader

    {registration}

    @pytest_data_loader.load("data", {rel_path!r})
    def test_something(data):
        ...
    """)
