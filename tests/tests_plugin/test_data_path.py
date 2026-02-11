import os
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester, RunResult

from pytest_data_loader import parametrize_dir
from pytest_data_loader.constants import ROOT_DIR
from pytest_data_loader.types import DataLoader
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR
from tests.tests_plugin.helper import (
    TestContext,
    create_test_context,
    create_test_data_in_data_dir,
    run_pytest_with_context,
)

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("value_type", [str, Path])
@pytest.mark.parametrize("dirs", ["foo", f"foo{os.sep}bar{os.sep}foobar"])
@pytest.mark.parametrize("is_abs_path", [False, True])
def test_loader_with_valid_data_path(
    pytester: Pytester,
    loader: DataLoader,
    is_abs_path: bool,
    dirs: Path | str,
    value_type: type[str | Path],
    collect_only: bool,
) -> None:
    """Test that valid relative paths are handled properly"""
    test_context = create_test_context(pytester, loader, path_type=value_type, is_abs_path=is_abs_path)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    "invalid_path", [".", "..", ROOT_DIR, Path(ROOT_DIR, "dir"), Path(ROOT_DIR, "dir", "test.txt")]
)
def test_loader_with_invalid_data_path(test_context: TestContext, invalid_path: str, collect_only: bool) -> None:
    """Test that invalid relative paths are handled properly"""
    result = run_pytest_with_context(test_context, path=invalid_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, invalid_path)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("is_abs_path", [False, True])
def test_loader_with_unmatched_data_path_type(
    test_context: TestContext, loader: DataLoader, data_dir_name: str, is_abs_path: bool, collect_only: bool
) -> None:
    """Test that relative path type that isn't allowed for each loader is handled properly"""
    file_path = create_test_data_in_data_dir(
        test_context.pytester, data_dir_name, Path("other_dir", "foo.txt"), return_abs_path=is_abs_path
    )
    if loader.is_file_loader:
        unmatched_path = file_path.parent
    else:
        unmatched_path = file_path
    result = run_pytest_with_context(test_context, path=unmatched_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, unmatched_path)


@pytest.mark.parametrize("collect_only", [True, False])
def test_loader_with_non_existing_data_path(test_context: TestContext, collect_only: bool) -> None:
    """Test that non-existing file or directory path is handled properly"""
    invalid_path = "foo"
    result = run_pytest_with_context(test_context, path=invalid_path, collect_only=collect_only)
    _check_result_with_invalid_path(result, test_context.loader, invalid_path)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("loader", [parametrize_dir])
def test_parametrize_dir_loader_with_no_file(test_context: TestContext, loader: DataLoader, collect_only: bool) -> None:
    """Test that parametrize_dir loader handles a directory with no file gracefully"""
    empty_dir = "empty_dir"
    test_context.pytester.mkdir(Path(test_context.data_dir) / empty_dir)
    result = run_pytest_with_context(test_context, path=empty_dir, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if collect_only:
        if pytest.version_tuple >= (8, 4):
            assert "NOTSET" in str(result.stdout)
    else:
        result.assert_outcomes(skipped=1)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("is_abs_path", [False, True])
@pytest.mark.parametrize("is_circular", [False, True])
def test_symlink(test_context: TestContext, is_circular: bool, is_abs_path: bool, collect_only: bool) -> None:
    """Test that symlinks are handled properly, including circular symlinks"""
    symlink_data_dir_name = "symlinks"
    src_symlink_data_dir = ABS_PATH_LOADER_DIR / symlink_data_dir_name
    dst = Path(test_context.data_dir) / symlink_data_dir_name
    if is_circular:
        src_symlink_data_dir /= "circular"
        dst.mkdir(exist_ok=True, parents=True)
        dst /= "circular"

    dst.symlink_to(src_symlink_data_dir, target_is_directory=True)

    if test_context.loader.is_file_loader:
        dir_or_filename = "symlink.txt"
    else:
        dir_or_filename = "symlink"

    if is_abs_path:
        path = dst / dir_or_filename
    else:
        path = dst.relative_to(test_context.data_dir) / dir_or_filename

    result = run_pytest_with_context(test_context, path=path, collect_only=collect_only)
    if is_circular:
        assert result.ret == ExitCode.INTERRUPTED
        assert "Detected a circular symlink" in str(result.stdout)
    else:
        assert result.ret == ExitCode.OK


def _check_result_with_invalid_path(result: RunResult, loader: DataLoader, invalid_path: Path | str) -> None:
    assert result.ret == ExitCode.INTERRUPTED
    stdout = str(result.stdout)
    result.assert_outcomes(errors=1)
    path = Path(invalid_path)
    if str(path) in (".", "..", ROOT_DIR):
        assert f"Invalid path value: '{path}'" in stdout
    elif path.is_absolute():
        if path.exists():
            assert (
                f"Invalid path: @{loader.__name__} loader must take a "
                f"{'file' if loader.is_file_loader and path.is_dir() else 'directory'} path, not '{path}'"
            ) in stdout
        else:
            assert f"The provided path does not exist: '{path}'" in stdout
    else:
        file_or_dir = "directory" if loader == parametrize_dir else "file"
        assert f"Unable to locate the specified {file_or_dir} '{path}'" in stdout
