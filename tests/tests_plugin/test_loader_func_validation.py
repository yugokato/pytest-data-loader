from pathlib import Path

import pytest
from pytest import ExitCode

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.types import DataLoader
from pytest_data_loader.utils import bind_and_call_loader_func, get_num_func_args
from tests.tests_plugin.helper import TestContext, run_pytest_with_context

SUPPORTED_LOADERS = {
    "onload_func": [load, parametrize],
    "parametrizer_func": [parametrize],
    "filter_func": [parametrize, parametrize_dir],
    "process_func": [parametrize, parametrize_dir],
    "id_func": [parametrize],
}


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:x", True, id="1arg"),
        pytest.param("lambda x,y:y", True, id="2args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda x,y,z:y", False, id="3args"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS["onload_func"])
def test_onload_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the onload_func parameter"""
    should_error_in_collection = loader == parametrize or not lazy_loading
    should_pass = is_valid or (collect_only and not should_error_in_collection)
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, onload_func_def=loader_func_def, collect_only=collect_only
    )
    if should_pass:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        if should_error_in_collection:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        else:
            assert result.ret == ExitCode.TESTS_FAILED
            result.assert_outcomes(errors=test_context.num_expected_tests)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            assert "Invalid loader function was provided. It supports up to 2 arguments" in str(result.stdout)
        else:
            assert f"Loader function must be a callable, not {type(loader_func).__name__}" in str(result.stdout)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:[x]", True, id="1arg"),
        pytest.param("lambda x,y:[y]", True, id="2args"),
        pytest.param("lambda x,y,z:[y]", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("lambda x:True", False, id="not_container"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS["parametrizer_func"])
def test_parametrizer_func_validation(
    test_context: TestContext,
    loader: DataLoader,
    loader_func_def: str,
    is_valid: bool,
    lazy_loading: bool,
    collect_only: bool,
) -> None:
    """Test validation around the parametrizer_func parameter for the following loaders"""
    should_error_in_collection = loader == parametrize or not lazy_loading
    should_pass = is_valid or (collect_only and not should_error_in_collection)
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, parametrizer_func_def=loader_func_def, collect_only=collect_only
    )
    if should_pass:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=1)
    else:
        if should_error_in_collection:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        else:
            # Placeholder. No valid scenario exists at the moment
            raise NotImplementedError("Test logic needs to be added")
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            num_args = get_num_func_args(loader_func)
            if 0 < num_args < 3:
                v = bind_and_call_loader_func(loader_func, Path("."), "foo")
                assert f"Parametrized data must be an iterable container, not {type(v).__name__}" in str(result.stdout)
            else:
                assert "Invalid loader function was provided. It supports up to 2 arguments" in str(result.stdout)
        else:
            assert f"Loader function must be a callable, not {type(loader_func).__name__}" in str(result.stdout)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:True", True, id="1arg"),
        pytest.param("lambda x,y:True", True, id="2args"),  # for parametrize
        pytest.param("lambda x,y:True", False, id="2args"),  # for parametrize_dir
        pytest.param("lambda x,y,z:True", False, id="3args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS["filter_func"])
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
    num_args = None
    if callable(loader_func):
        num_args = get_num_func_args(loader_func)
        if num_args == 2:
            if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                pytest.skip("Not applicable")

    should_error_in_collection = (
        loader == parametrize or (loader == parametrize_dir and num_args != 1) or not lazy_loading
    )
    should_pass = is_valid or (collect_only and not should_error_in_collection)

    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, filter_func_def=loader_func_def, collect_only=collect_only
    )
    if should_pass:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        if should_error_in_collection:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        else:
            # Placeholder. No valid scenario exists at the moment
            raise NotImplementedError("Test logic needs to be added")
        if callable(loader_func):
            max_allowed = 1 if loader == parametrize_dir else 2
            assert f"Invalid loader function was provided. It supports up to {max_allowed} arguments" in str(
                result.stdout
            )
        else:
            assert f"Loader function must be a callable, not {type(loader_func).__name__}" in str(result.stdout)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    ("loader_func_def", "is_valid"),
    [
        pytest.param("lambda x:x", True, id="1arg"),
        pytest.param("lambda x,y:y", True, id="2args"),
        pytest.param("lambda:True", False, id="0arg"),
        pytest.param("True", False, id="not_callable"),
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", SUPPORTED_LOADERS["process_func"])
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
    should_error_in_collection = not lazy_loading
    should_pass = is_valid or (collect_only and not should_error_in_collection)
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, process_func_def=loader_func_def, collect_only=collect_only
    )
    if should_pass:
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)
    else:
        if should_error_in_collection:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
        else:
            assert result.ret == ExitCode.TESTS_FAILED
            result.assert_outcomes(errors=test_context.num_expected_tests)
        loader_func = eval(f"{loader_func_def}")
        if callable(loader_func):
            assert "Invalid loader function was provided. It supports up to 2 arguments" in str(result.stdout)
        else:
            assert f"Loader function must be a callable, not {type(loader_func).__name__}" in str(result.stdout)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("loader", [parametrize])
def test_parametrize_binary_file_with_no_custom_parametrizer_func(
    loader: DataLoader, test_context: TestContext, png_file_content: bytes, collect_only: bool
) -> None:
    """Test that @parametrize loader properly blocks binary data when a custom parametrizer logic is not provided"""
    relative_file_path = "image.png"
    pytester = test_context.pytester
    (pytester.path / DEFAULT_LOADER_DIR_NAME / relative_file_path).write_bytes(png_file_content)
    result = run_pytest_with_context(test_context, relative_data_path=relative_file_path, collect_only=collect_only)
    assert result.ret == ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    assert "binary data requires a custom parametrizer function" in str(result.stdout)
