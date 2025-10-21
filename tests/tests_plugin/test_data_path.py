import os
from pathlib import Path

import pytest
from pytest import ExitCode, RunResult

from pytest_data_loader import parametrize_dir
from pytest_data_loader.constants import ROOT_DIR
from pytest_data_loader.types import DataLoader
from tests.tests_plugin.helper import TestContext, create_test_file_in_loader_dir, run_pytest_with_context

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("value_type", [str, Path])
@pytest.mark.parametrize("relative_dir", ["foo", f"foo{os.sep}bar{os.sep}foobar"])
def test_loader_with_valid_data_path(
    test_context: TestContext, relative_dir: Path | str, value_type: type, collect_only: bool
) -> None:
    """Test that valid relative paths are handled properly"""
    relative_path = create_test_file_in_loader_dir(
        test_context.pytester, test_context.loader_dir, relative_dir, is_dir=True, file_name="test.txt"
    )
    if not test_context.loader.requires_file_path:
        relative_path = relative_path.parent
    path: Path | str
    if value_type is str:
        path = str(relative_path)
    else:
        path = relative_path
    result = run_pytest_with_context(test_context, relative_data_path=path, collect_only=collect_only)
    assert result.ret == ExitCode.OK


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("invalid_path", [".", "..", ROOT_DIR])
def test_loader_with_invalid_data_path(test_context: TestContext, invalid_path: str, collect_only: bool) -> None:
    """Test that invalid relative paths are handled properly"""
    result = run_pytest_with_context(test_context, relative_data_path=invalid_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, invalid_path)


@pytest.mark.parametrize("collect_only", [True, False])
def test_loader_with_unmatched_data_path_type(test_context: TestContext, collect_only: bool) -> None:
    """Test that relative path type that isn't allowed for each loader is handled properly"""
    pytester = test_context.pytester
    file_path = create_test_file_in_loader_dir(pytester, "some_dir", Path(f"other_dir{os.sep}foo.txt"))
    if test_context.loader.requires_file_path:
        unmatched_path = file_path.parent
    else:
        unmatched_path = file_path
    result = run_pytest_with_context(test_context, relative_data_path=unmatched_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, unmatched_path)


@pytest.mark.parametrize("collect_only", [True, False])
def test_loader_with_non_existing_data_path(test_context: TestContext, collect_only: bool) -> None:
    """Test that non-existing file or directory path is handled properly"""
    invalid_path = "foo"
    result = run_pytest_with_context(test_context, relative_data_path=invalid_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, invalid_path)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("loader", [parametrize_dir])
def test_parametrize_dir_loader_with_no_file(test_context: TestContext, loader: DataLoader, collect_only: bool) -> None:
    """Test that parametrize_dir loader handles a directory with no file gracefully"""
    empty_dir = "empty_dir"
    test_context.pytester.mkdir(Path(test_context.loader_dir) / empty_dir)
    result = run_pytest_with_context(test_context, relative_data_path=empty_dir, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if collect_only:
        if pytest.version_tuple >= (8, 4):
            assert "NOTSET" in str(result.stdout)
    else:
        result.assert_outcomes(skipped=1)


def _check_result_with_invalid_path(result: RunResult, loader: DataLoader, invalid_path: Path | str) -> None:
    assert result.ret == ExitCode.INTERRUPTED
    stdout = str(result.stdout)
    result.assert_outcomes(errors=1)
    if Path(invalid_path).is_absolute():
        assert "It can not be an absolute path" in stdout
    elif str(invalid_path) in (".", "..", os.sep):
        assert f"Invalid relative_path value: '{invalid_path}'" in stdout
    else:
        file_or_dir = "directory" if loader == parametrize_dir else "file"
        assert f"Unable to locate the specified {file_or_dir} '{invalid_path}'" in stdout
