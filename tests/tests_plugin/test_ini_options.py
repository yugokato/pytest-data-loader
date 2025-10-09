import os

import pytest
from pytest import ExitCode

from pytest_data_loader.types import DataLoaderIniOption
from tests.tests_plugin.helper import TestContext, run_pytest_with_context


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("loader_dir_name", ["data", "new_dir", ".test"], indirect=True)
def test_ini_option_data_loader_dir_name(test_context: TestContext, collect_only: bool, loader_dir_name: str) -> None:
    """Test data_loader_dir_name INI option with valid names"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_DIR_NAME} = {loader_dir_name}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("strip_trailing_whitespace", ["true", "false"], indirect=True)
def test_ini_option_data_loader_strip_trailing_whitespace(
    test_context: TestContext, collect_only: bool, strip_trailing_whitespace: str
) -> None:
    """Test data_loader_strip_trailing_whitespace INI option with valid names"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE} = {strip_trailing_whitespace}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("invalid_dir_name", ["", ".", "..", os.sep, f"{os.sep}foo", f"foo{os.sep}bar"])
def test_ini_option_data_loader_dir_name_invalid(
    test_context: TestContext, collect_only: bool, invalid_dir_name: str
) -> None:
    """Test data_loader_dir_name INI option with invalid names"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_DIR_NAME} = {invalid_dir_name}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.USAGE_ERROR
    assert f"INI option {DataLoaderIniOption.DATA_LOADER_DIR_NAME}: Invalid value: '{invalid_dir_name}'" in str(
        result.stderr
    )


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("invalid_value", ["", "foo"])
def test_ini_option_data_loader_strip_trailing_whitespace_invalid(
    test_context: TestContext, collect_only: bool, invalid_value: str
) -> None:
    """Test data_loader_strip_trailing_whitespace INI option with invalid values"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE} = {invalid_value}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.USAGE_ERROR
    assert (
        f"INI option {DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE}: invalid truth value '{invalid_value}'"
        in str(result.stderr)
    )
