from pathlib import Path

import pytest
from pytest import ExitCode

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType
from pytest_data_loader.utils import validate_loader_func_args_and_normalize
from tests.tests_plugin.helper import TestContext, get_num_func_args, run_pytest_with_context

pytestmark = pytest.mark.plugin


SUPPORTED_LOADERS = {
    DataLoaderFunctionType.ONLOAD_FUNC: [load, parametrize],
    DataLoaderFunctionType.PARAMETRIZER_FUNC: [parametrize],
    DataLoaderFunctionType.FILTER_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.PROCESS_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.MARKER_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.ID_FUNC: [parametrize],
    DataLoaderFunctionType.FILE_READER_FUNC: [parametrize_dir],
    DataLoaderFunctionType.READ_OPTION_FUNC: [parametrize_dir],
}


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:x", True, id="1arg"),
        pytest.param("lambda x,y:y", True, id="2args"),
        pytest.param("lambda x,y,z:y", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda *args:args", False, id="*args"),
        pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.ONLOAD_FUNC])
def test_onload_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the onload_func parameter"""
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, onload_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            err = f"Detected invalid {DataLoaderFunctionType.ONLOAD_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            else:
                assert f"{err} It must take up to 2 arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.ONLOAD_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:[x]", True, id="1arg"),
        pytest.param("lambda x,y:[y]", True, id="2args"),
        pytest.param("lambda x,y,z:[y]", False, id="3args"),
        pytest.param("lambda:[True]", False, id="0arg"),
        pytest.param("lambda x:True", False, id="not_container"),
        pytest.param("lambda *args:args", False, id="*args"),
        pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.PARAMETRIZER_FUNC])
def test_parametrizer_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the parametrizer_func parameter for the following loaders"""
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, parametrizer_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=1)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            num_args = get_num_func_args(loader_func)
            if 0 < num_args < 3 and "*" not in loader_func_def:
                f = validate_loader_func_args_and_normalize(loader_func)
                v = f(Path("."), "foo")
                assert f"Parametrized data must be an iterable container, not {type(v).__name__!r}" in str(
                    result.stdout
                )
            else:
                err = f"Detected invalid {DataLoaderFunctionType.PARAMETRIZER_FUNC} loader function definition."
                if "*" in loader_func_def:
                    assert f"{err} Only positional arguments are allowed" in str(result.stdout)
                else:
                    assert f"{err} It must take up to 2 arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.PARAMETRIZER_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:True", True, id="1arg"),
        pytest.param("lambda x,y:True", True, id="2args"),  # for parametrize
        pytest.param("lambda x,y:True", False, id="2args"),  # for parametrize_dir
        pytest.param("lambda x,y,z:True", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda *args:True", False, id="*args"),
        pytest.param("lambda **kwargs:True", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.FILTER_FUNC])
def test_filter_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the filter_func parameter for parametrize loader"""

    loader_func = eval(f"{loader_func_def}")
    if callable(loader_func):
        num_args = get_num_func_args(loader_func)
        if num_args == 2:
            if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                pytest.skip("Not applicable")

    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, filter_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        if callable(loader_func):
            err = f"Detected invalid {DataLoaderFunctionType.FILTER_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            else:
                max_allowed = 1 if loader == parametrize_dir else 2
                assert f"{err} It must take up to {max_allowed} arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.FILTER_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:x", True, id="1arg"),
        pytest.param("lambda x,y:y", True, id="2args"),
        pytest.param("lambda x,y,z:True", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda *args:args", False, id="*args"),
        pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.PROCESS_FUNC])
def test_process_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the process_func parameter

    NOTE: If lazy loading is enabled, the test collection will never fail because the loader function will
          not be called until after the data is actually loaded
    """
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, process_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            err = f"Detected invalid {DataLoaderFunctionType.PROCESS_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            else:
                assert f"{err} It must take up to 2 arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.PROCESS_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:pytest.mark.foo", True, id="1arg"),
        pytest.param("lambda x,y:pytest.mark.foo", True, id="2args"),  # for parametrize
        pytest.param("lambda x,y:pytest.mark.foo", False, id="2args"),  # for parametrize_dir
        pytest.param("lambda x,y,z:pytest.mark.foo", False, id="3args"),
        pytest.param("lambda:pytest.mark.foo", False, id="0arg"),
        pytest.param("lambda *args:args", False, id="*args"),
        pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.MARKER_FUNC])
def test_marker_func_test_marker_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the marker_func parameter"""
    loader_func = eval(f"{loader_func_def}")
    if callable(loader_func):
        num_args = get_num_func_args(loader_func)
        if num_args == 2:
            if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                pytest.skip("Not applicable")

    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, marker_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        if callable(loader_func):
            max_allowed = 1 if loader == parametrize_dir else 2
            err = f"Detected invalid {DataLoaderFunctionType.MARKER_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            else:
                assert f"{err} It must take up to {max_allowed} arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.MARKER_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:x", True, id="1arg"),
        pytest.param("lambda x,y:y", True, id="2args"),
        pytest.param("lambda x,y,z:True", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda *args:args", False, id="*args"),
        pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.ID_FUNC])
def test_id_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the id_func parameter"""
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, id_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            err = f"Detected invalid {DataLoaderFunctionType.ID_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            else:
                assert f"{err} It must take up to 2 arguments" in str(result.stdout)
        else:
            assert f"{DataLoaderFunctionType.ID_FUNC}: Must be a callable, not {type(loader_func).__name__!r}" in str(
                result.stdout
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:{}", True, id="1arg"),
        pytest.param("lambda x,y:{}", False, id="2args"),
        pytest.param("lambda x,y,z:{}", False, id="3args"),
        pytest.param("lambda:{}", False, id="0arg"),
        pytest.param("lambda *args:{}", False, id="*args"),
        pytest.param("lambda **kwargs:{}", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
        pytest.param("lambda x:x", False, id="invalid_value"),
        pytest.param("lambda x:{'mode': 'w'}", False, id="invalid_read_mode"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.READ_OPTION_FUNC])
def test_read_option_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the read_option_func parameter"""
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, read_option_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            num_args = get_num_func_args(loader_func)
            max_allowed = 1 if loader == parametrize_dir else 2
            err = f"Detected invalid {DataLoaderFunctionType.READ_OPTION_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            elif num_args == 1:
                if "mode" in loader_func_def:
                    assert "read_options: Invalid read mode: " in str(result.stdout)
                else:
                    assert "read_options: Expected a dict, but got " in str(result.stdout)
            else:
                assert f"{err} It must take up to {max_allowed} arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.READ_OPTION_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:json.load", True, id="1arg"),
        pytest.param("lambda x,y:json.load", False, id="2args"),
        pytest.param("lambda x,y,z:json.load", False, id="3args"),
        pytest.param("lambda:json.load", False, id="0arg"),
        pytest.param("lambda *args:json.load", False, id="*args"),
        pytest.param("lambda **kwargs:json.load", False, id="**kwargs"),
        pytest.param("True", False, id="not_callable"),
        pytest.param("lambda x:True", False, id="invalid_value"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("file_extension", [".json"], indirect=True)
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.FILE_READER_FUNC])
def test_file_reader_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    file_extension: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the file_reader_func parameter"""
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, file_reader_func_def=loader_func_def, collect_only=collect_only
    )
    if is_valid:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            num_args = get_num_func_args(loader_func)
            max_allowed = 1 if loader == parametrize_dir else 2
            err = f"Detected invalid {DataLoaderFunctionType.FILE_READER_FUNC} loader function definition."
            if "*" in loader_func_def:
                assert f"{err} Only positional arguments are allowed" in str(result.stdout)
            elif num_args == 1:
                assert "file_reader: Expected an iterable or a callable, but got " in str(result.stdout)
            else:
                assert f"{err} It must take up to {max_allowed} arguments" in str(result.stdout)
        else:
            assert (
                f"{DataLoaderFunctionType.FILE_READER_FUNC}: Must be a callable, not {type(loader_func).__name__!r}"
                in str(result.stdout)
            )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("loader", [parametrize])
def test_parametrize_binary_file_with_no_custom_parametrizer_func(
    loader: DataLoader, test_context: TestContext, png_file_content: bytes, collect_only: bool
) -> None:
    """Test that @parametrize loader properly blocks binary data when a custom parametrizer logic is not provided"""
    relative_file_path = "image.png"
    pytester = test_context.pytester
    (pytester.path / DEFAULT_LOADER_DIR_NAME / relative_file_path).write_bytes(png_file_content)
    result = run_pytest_with_context(test_context, path=relative_file_path, collect_only=collect_only)
    assert result.ret == ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    assert f"@{loader.__name__} loader requires a custom parametrizer function for binary data" in str(result.stdout)
