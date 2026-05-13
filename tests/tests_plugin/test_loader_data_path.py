import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest import ExitCode, MonkeyPatch, Pytester, RunResult

from pytest_data_loader import parametrize_dir
from pytest_data_loader.constants import ROOT_DIR
from pytest_data_loader.types import DataLoader
from tests.paths import ABS_PATH_LOADER_DIR

from .helper import TestContext, create_test_context, create_test_data_in_data_dir, run_pytest_with_context

if sys.platform == "win32":
    ENV_VAR = "%FOO%"
else:
    ENV_VAR = "${FOO}"

pytestmark = pytest.mark.plugin


class TestLoaderDataPath:
    """Tests for data path handling in loaders."""

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("value_type", [str, Path])
    @pytest.mark.parametrize("dirs", ["foo", f"foo{os.sep}bar{os.sep}foobar"])
    @pytest.mark.parametrize("is_abs_path", [False, True])
    def test_loader_with_valid_data_path(
        self,
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
    def test_loader_with_invalid_data_path(
        self, test_context: TestContext, invalid_path: str, collect_only: bool
    ) -> None:
        """Test that invalid relative paths are handled properly"""
        result = run_pytest_with_context(test_context, path=invalid_path, collect_only=collect_only)
        self._check_result_with_invalid_path(result, test_context.loader, invalid_path)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("is_abs_path", [False, True])
    def test_loader_with_unmatched_data_path_type(
        self, test_context: TestContext, loader: DataLoader, data_dir_name: str, is_abs_path: bool, collect_only: bool
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
        self._check_result_with_invalid_path(result, test_context.loader, unmatched_path)

    @pytest.mark.parametrize("collect_only", [True, False])
    def test_loader_with_non_existing_data_path(self, test_context: TestContext, collect_only: bool) -> None:
        """Test that non-existing file or directory path is handled properly"""
        invalid_path = "foo"
        result = run_pytest_with_context(test_context, path=invalid_path, collect_only=collect_only)
        self._check_result_with_invalid_path(result, test_context.loader, invalid_path)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("loader", [parametrize_dir])
    def test_parametrize_dir_loader_with_no_file(
        self, test_context: TestContext, loader: DataLoader, collect_only: bool
    ) -> None:
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
    def test_symlink(self, test_context: TestContext, is_circular: bool, is_abs_path: bool, collect_only: bool) -> None:
        """Test that symlinks are handled properly, including circular symlinks (ELOOP and directory
        traversal cycles)"""
        src_symlink_data_dir = ABS_PATH_LOADER_DIR / "symlinks"
        dst = Path(test_context.data_dir) / src_symlink_data_dir.name
        dst.symlink_to(src_symlink_data_dir, target_is_directory=True)

        kwargs: dict[str, Any] = {}
        if test_context.loader.is_file_loader:
            dir_or_file = Path("symlink.txt")
        else:
            dir_or_file = Path("dir", "symlink")
            kwargs.update(recursive=True)

        if is_circular:
            dir_or_file = Path("circular", dir_or_file)

        if is_abs_path:
            path = dst / dir_or_file
        else:
            path = dst.relative_to(test_context.data_dir) / dir_or_file

        result = run_pytest_with_context(test_context, path=path, collect_only=collect_only, **kwargs)
        if is_circular:
            assert result.ret == ExitCode.INTERRUPTED
            assert "Detected a circular symlink" in str(result.stdout)
        else:
            assert result.ret == ExitCode.OK

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("is_abs_path", [False, True])
    @pytest.mark.parametrize(
        "env_var",
        [ENV_VAR, pytest.param("$FOO", marks=pytest.mark.skipif(sys.platform == "win32", reason="Not for windows"))],
    )
    def test_env_var_in_path(
        self,
        test_context: TestContext,
        monkeypatch: MonkeyPatch,
        env_var: str,
        collect_only: bool,
        is_abs_path: bool,
    ) -> None:
        """Test that env-var references in an absolute/relative path are expanded before the loader resolves it."""
        loader = test_context.loader
        subdir = "subdir"
        env_var_name = re.sub(r"\W", "", env_var)
        file_path = create_test_data_in_data_dir(
            test_context.pytester,
            Path(test_context.data_dir).name,
            Path(subdir, f"file{test_context.test_file_ext}"),
            data=test_context.test_file_content,
            return_abs_path=is_abs_path,
        )
        if loader.is_file_loader:
            monkeypatch.setenv(env_var_name, str(file_path.parent))
            path = f"{env_var}{os.sep}{file_path.name}"
            num_tests = test_context.num_expected_tests
        else:
            dir_path = file_path.parent
            path = f"{env_var}{os.sep}{dir_path.name}"
            monkeypatch.setenv(env_var_name, str(dir_path.parent))
            num_tests = 1

        result = run_pytest_with_context(test_context, path=path, collect_only=collect_only)
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=num_tests)

    @pytest.mark.parametrize("collect_only", [True, False])
    def test_unresolved_env_var_in_path(self, test_context: TestContext, collect_only: bool) -> None:
        """Test that an unresolved env-var reference in a path raises a clear error."""
        path = f"{ENV_VAR}{os.sep}file.txt"
        result = run_pytest_with_context(test_context, path=path, collect_only=collect_only)
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert "Unable to resolve environment variable(s) in the path" in str(result.stdout)

    @staticmethod
    def _check_result_with_invalid_path(result: RunResult, loader: DataLoader, invalid_path: Path | str) -> None:
        assert result.ret == ExitCode.INTERRUPTED
        stdout = str(result.stdout)
        result.assert_outcomes(errors=1)
        path = Path(invalid_path)
        if str(path) in (".", "..", ROOT_DIR):
            assert f"Invalid path value: {str(path)!r}" in stdout
        elif path.is_absolute():
            if path.exists():
                assert (
                    f"Invalid path type: @{loader.__name__} loader must take a "
                    f"{'file' if loader.is_file_loader and path.is_dir() else 'directory'} path, not {str(path)!r}"
                ) in stdout
            else:
                assert f"The provided path does not exist: {str(path)!r}" in stdout
        else:
            file_or_dir = "directory" if loader == parametrize_dir else "file"
            assert f"Unable to locate the {file_or_dir} {str(path)!r}" in stdout
