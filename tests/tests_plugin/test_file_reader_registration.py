import os
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
    ext = ".txt"
    rel_path, file_data = _setup_data(pytester, ext=ext)
    if register or override:
        _create_conftest_with_reader_registration(pytester, "io.TextIOWrapper", ext=ext, read_options={"mode": "rb"})
    if override:
        reader_def = ", file_reader=io.BufferedReader"
    else:
        reader_def = ""
    pytester.makepyfile(f"""
    import io
    from pathlib import Path

    import pytest_data_loader
    from pytest_data_loader.loaders.reader import FileReader

    register = {register}
    override = {override}

    @pytest_data_loader.load("data", {rel_path!r}{reader_def})
    def test_something(data):
        if register or override:
            registered_file_reader = FileReader.get_registered_reader(Path(__file__), {ext!r})
            assert registered_file_reader.reader == io.TextIOWrapper
            if override:
                assert isinstance(data, io.BufferedReader)
            else:
                assert isinstance(data, io.TextIOWrapper)
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
    ext = ".txt"
    rel_path, _ = _setup_data(pytester, ext=ext)

    # Register reader in the top-level confest.py
    _create_conftest_with_reader_registration(pytester, "io.TextIOWrapper", read_options={"mode": "rb"})

    # Create a child dir with empty conftest.py in it
    p = pytester.mkdir("tests_something")
    pytester._path = p
    pytester.chdir()
    pytester.makeconftest("")

    # Create another child dir and register a different reader in confest.py
    p = pytester.mkdir("tests_something2")
    pytester._path = p
    pytester.chdir()
    _create_conftest_with_reader_registration(pytester, "io.BufferedReader", read_options={"mode": "rb"})

    # Create test file
    pytester.makepyfile(f"""
       import io
       from pathlib import Path

       import pytest_data_loader
       from pytest_data_loader.loaders.reader import FileReader

       @pytest_data_loader.load("data", {rel_path!r})
       def test_something(data):
           file_reader = FileReader.get_registered_reader(Path(__file__), {ext!r})
           assert file_reader.reader == io.BufferedReader
           assert isinstance(data, io.BufferedReader)
       """)

    pytester._path = orig_dir
    pytester.chdir()

    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1)


def test_file_reader_registration_with_invalid_extension(pytester: Pytester) -> None:
    """Test that file extension is validated during registration"""
    rel_path, _ = _setup_data(pytester)
    _create_conftest_with_reader_registration(pytester, "io.TextIOWrapper", ext="foo")
    _create_test_for_negative_cases(pytester, rel_path)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.USAGE_ERROR
    assert "File extension must start with '.'" in str(result.stderr)


def test_file_reader_registration_with_invalid_reader(pytester: Pytester) -> None:
    """Test that file reader is validated during registration"""
    rel_path, _ = _setup_data(pytester)
    _create_conftest_with_reader_registration(pytester, '"foo"')
    _create_test_for_negative_cases(pytester, rel_path)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.USAGE_ERROR
    assert "file_reader: Expected an iterable or a callable" in str(result.stderr)


def test_file_reader_registration_with_invalid_read_options(pytester: Pytester) -> None:
    """Test that file read option is validated during registration"""
    rel_path, _ = _setup_data(pytester)
    _create_conftest_with_reader_registration(pytester, "io.TextIOWrapper", read_options={"mode": "w"})
    _create_test_for_negative_cases(pytester, rel_path)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.USAGE_ERROR
    assert "read_options: Invalid read mode" in str(result.stderr)


def test_file_reader_registration_in_non_conftest(pytester: Pytester) -> None:
    """Test that reader registration is not allowed outside conftest.py"""
    ext = ".txt"
    rel_path, _ = _setup_data(pytester, ext=ext)
    _create_test_for_negative_cases(pytester, rel_path, register_reader=True)
    result = pytester.runpytest_subprocess()
    assert result.ret == ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    assert "pytest_data_loader.register_reader() must be called from a conftest.py" in str(result.stdout)


def _setup_data(pytester: Pytester, ext: str = ".txt") -> tuple[str, str]:
    pytester.mkdir(DEFAULT_LOADER_DIR_NAME)
    rel_path = f"test{ext}"
    name, ext = os.path.splitext(rel_path)
    file_data = "foo\nbar\nfoobar"
    pytester.makefile(ext, **{str(Path(DEFAULT_LOADER_DIR_NAME, name)): file_data})
    return rel_path, file_data


def _create_conftest_with_reader_registration(
    pytester: Pytester,
    reader_def: str,
    ext: str = ".txt",
    read_options: dict[str, Any] | None = None,
) -> None:
    if read_options:
        read_option_def = ", ".join(f"{k}={v!r}" for k, v in read_options.items())
    else:
        read_option_def = ""
    pytester.makeconftest(f"""
    import io
    import pytest_data_loader

    pytest_data_loader.register_reader({ext!r}, {reader_def}, {read_option_def})
    """)


def _create_test_for_negative_cases(pytester: Pytester, rel_path: str, register_reader: bool = False) -> Path:
    return pytester.makepyfile(f"""
    import io
    from pathlib import Path
    import pytest_data_loader

    if {register_reader}:
        pytest_data_loader.register_reader({Path(rel_path).suffix!r}, "io.TextIOWrapper")

    @pytest_data_loader.load("data", {rel_path!r})
    def test_something(data):
        ...
    """)
