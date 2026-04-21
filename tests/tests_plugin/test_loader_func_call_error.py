from dataclasses import dataclass, field

import pytest
from pytest import ExitCode, Pytester, RunResult

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType

pytestmark = pytest.mark.plugin


@dataclass(frozen=True, kw_only=True)
class Case:
    """Definition of a single loader-func-error test scenario."""

    func_type: DataLoaderFunctionType
    loader: DataLoader
    func_params: str
    file_name: str
    file_content: str
    file_ext: str
    data_path: str
    is_dir_setup: bool = False
    expected_exit_lazy: ExitCode
    expected_exit_eager: ExitCode = field(default=ExitCode.INTERRUPTED)  # always INTERRUPTED


CASES = (
    Case(
        func_type=DataLoaderFunctionType.ONLOAD_FUNC,
        loader=load,
        func_params="d",
        file_name="data",
        file_content='{"key": "value"}',
        file_ext=".json",
        data_path="data.json",
        expected_exit_lazy=ExitCode.TESTS_FAILED,
    ),
    Case(
        func_type=DataLoaderFunctionType.PARAMETRIZER_FUNC,
        loader=parametrize,
        func_params="d",
        file_name="data",
        file_content="foo\nbar",
        file_ext=".txt",
        data_path="data.txt",
        expected_exit_lazy=ExitCode.INTERRUPTED,
    ),
    Case(
        func_type=DataLoaderFunctionType.FILTER_FUNC,
        loader=parametrize,
        func_params="d",
        file_name="data",
        file_content="foo\nbar",
        file_ext=".txt",
        data_path="data.txt",
        expected_exit_lazy=ExitCode.INTERRUPTED,
    ),
    Case(
        func_type=DataLoaderFunctionType.PROCESS_FUNC,
        loader=parametrize,
        func_params="d",
        file_name="data",
        file_content="foo\nbar",
        file_ext=".txt",
        data_path="data.txt",
        expected_exit_lazy=ExitCode.TESTS_FAILED,
    ),
    Case(
        func_type=DataLoaderFunctionType.ID_FUNC,
        loader=parametrize,
        func_params="p, d",
        file_name="data",
        file_content="foo\nbar",
        file_ext=".txt",
        data_path="data.txt",
        expected_exit_lazy=ExitCode.INTERRUPTED,
    ),
    Case(
        func_type=DataLoaderFunctionType.MARKER_FUNC,
        loader=parametrize,
        func_params="p, d",
        file_name="data",
        file_content="foo\nbar",
        file_ext=".txt",
        data_path="data.txt",
        expected_exit_lazy=ExitCode.INTERRUPTED,
    ),
    Case(
        func_type=DataLoaderFunctionType.READ_OPTION_FUNC,
        loader=parametrize_dir,
        func_params="p",
        file_name="file1",
        file_content="hello",
        file_ext=".txt",
        data_path="mydir",
        expected_exit_lazy=ExitCode.INTERRUPTED,
    ),
)


class TestLoaderFuncCallError:
    """Tests that loader function call errors include the file name in the exception message."""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("case", CASES, ids=lambda c: str(c.func_type))
    def test_loader_func_call_error(self, pytester: Pytester, case: Case, lazy_loading: bool) -> None:
        """Test that errors raised inside loader callbacks report the file name in the exception message."""
        result = _run_test(pytester, case, lazy_loading)
        expected_exit = case.expected_exit_lazy if lazy_loading else case.expected_exit_eager
        output = str(result.stdout)
        assert result.ret == expected_exit
        assert "ValueError: loader func error" in output
        assert f"Error while processing {case.func_type} for {case.file_name + case.file_ext!r}" in output


def _run_test(pytester: Pytester, case: Case, lazy_loading: bool) -> RunResult:
    """Build the inner test for a loader-func-error case, run it, and return the result."""
    if case.loader.is_file_loader:
        pytester.mkdir("data")
        pytester.makefile(case.file_ext, **{f"data/{case.file_name}": case.file_content})
    else:
        data_dir = pytester.mkdir("data") / case.data_path
        data_dir.mkdir()
        (data_dir / (case.file_name + case.file_ext)).write_text(case.file_content)

    pytester.makepyfile(f"""
    from pytest_data_loader import {case.loader.__name__}

    def f({case.func_params}):
        raise ValueError("loader func error")

    @{case.loader.__name__}("data", "{case.data_path}", lazy_loading={lazy_loading}, {case.func_type}=f)
    def test_func(data):
        pass
    """)
    return pytester.runpytest()
