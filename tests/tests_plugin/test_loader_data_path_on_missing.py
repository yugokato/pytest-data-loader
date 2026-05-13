from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

from pytest_data_loader.types import DataLoaderIniOption, DataLoaderOnMissingAction

from .helper import TestContext, run_pytest_with_context

pytestmark = pytest.mark.plugin


class TestMissingDataPath:
    """Tests missing data path with on_missing options"""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("on_missing", DataLoaderOnMissingAction)
    def test_on_missing_path(
        self, test_context: TestContext, is_abs: bool, lazy_loading: bool, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test that on_missing governs behavior when a data path does not exist."""
        path = "does_not_exist"
        if is_abs:
            path = str(Path(test_context.data_dir) / path)
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        result = run_pytest_with_context(test_context, path=path, lazy_loading=lazy_loading)
        if on_missing == DataLoaderOnMissingAction.RAISE:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        elif on_missing == DataLoaderOnMissingAction.WARN:
            # warn: test runs with None data and fails on its type assertion
            assert result.ret == ExitCode.TESTS_FAILED
            result.assert_outcomes(failed=1)
        else:
            assert result.ret == ExitCode.OK
            if on_missing == DataLoaderOnMissingAction.SKIP:
                result.assert_outcomes(skipped=1)
            else:
                result.assert_outcomes(xfailed=1)

        output = str(result.stdout)
        if on_missing == DataLoaderOnMissingAction.WARN:
            result.stdout.fnmatch_lines("*UserWarning: DataNotFound:*")
        else:
            assert "UserWarning: DataNotFound:" not in output

        if on_missing != DataLoaderOnMissingAction.RAISE:
            result.stdout.fnmatch_lines("*:MISSING]*")


class TestMissingDataPathWithGlob:
    """Tests for on_missing behavior with glob patterns that match nothing."""

    @pytest.fixture(autouse=True)
    def data_dir(self, pytester: Pytester) -> Path:
        return pytester.mkdir("data")

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("on_missing", DataLoaderOnMissingAction)
    def test_on_missing_glob_no_matching_file(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test that on_missing governs behavior when a file glob matches nothing."""
        pattern = "foo/*.txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", {pattern!r})
        def test_func(data):
            ...
        """)
        result = pytester.runpytest("-v")
        if on_missing == DataLoaderOnMissingAction.RAISE:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        elif on_missing == DataLoaderOnMissingAction.WARN:
            # warn: test runs with None data; test body is `...` so it passes
            assert result.ret == ExitCode.OK
            result.assert_outcomes(passed=1)
        else:
            assert result.ret == ExitCode.OK
            if on_missing == DataLoaderOnMissingAction.SKIP:
                result.assert_outcomes(skipped=1)
            else:
                result.assert_outcomes(xfailed=1)

        if on_missing == DataLoaderOnMissingAction.WARN:
            result.stdout.fnmatch_lines("*UserWarning: DataNotFound:*")
        else:
            assert "UserWarning: DataNotFound:" not in str(result.stdout)

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("on_missing", DataLoaderOnMissingAction)
    def test_on_missing_glob_no_matching_dir(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test that on_missing governs behavior when a directory glob matches nothing."""
        pattern = "foo/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", {pattern!r})
        def test_func(data):
            ...
        """)
        result = pytester.runpytest("-v")
        if on_missing == DataLoaderOnMissingAction.RAISE:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        elif on_missing == DataLoaderOnMissingAction.WARN:
            # warn: test runs with None data; test body is `...` so it passes
            assert result.ret == ExitCode.OK
            result.assert_outcomes(passed=1)
        else:
            assert result.ret == ExitCode.OK
            if on_missing == DataLoaderOnMissingAction.SKIP:
                result.assert_outcomes(skipped=1)
            else:
                result.assert_outcomes(xfailed=1)

        if on_missing == DataLoaderOnMissingAction.WARN:
            result.stdout.fnmatch_lines("*UserWarning: DataNotFound:*")
        else:
            assert "UserWarning: DataNotFound:" not in str(result.stdout)
