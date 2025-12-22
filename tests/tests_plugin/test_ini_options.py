import os
import sys

import pytest
from pytest import ExitCode

from pytest_data_loader import load
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME, ROOT_DIR
from pytest_data_loader.types import DataLoader, DataLoaderIniOption
from tests.tests_plugin.helper import (
    LoaderRootDir,
    TestContext,
    create_test_data_in_data_dir,
    run_pytest_with_context,
)

pytestmark = pytest.mark.plugin


if sys.platform == "win32":
    ENV_VAR = "%FOO%"
else:
    ENV_VAR = "${FOO}"


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("data_dir_name", [DEFAULT_LOADER_DIR_NAME, "new_dir", ".test"], indirect=True)
def test_ini_option_data_loader_dir_name(test_context: TestContext, collect_only: bool, data_dir_name: str) -> None:
    """Test data_loader_dir_name INI option with valid names"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_DIR_NAME} = {data_dir_name}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    "loader_root_dir",
    [
        f"..{os.sep}",
        ENV_VAR,
        pytest.param("$FOO", marks=pytest.mark.skipif(sys.platform == "win32", reason="Not for windows")),
        ENV_VAR + os.sep + "bar",
    ],
    indirect=True,
)
@pytest.mark.parametrize("loader", [load])
def test_ini_option_data_loader_root_dir(
    loader: DataLoader, test_context: TestContext, collect_only: bool, loader_root_dir: LoaderRootDir
) -> None:
    """Test data_loader_root_dir INI option with valid names"""
    assert loader_root_dir.requested_path is not None
    assert loader_root_dir.requested_path.startswith(("..", ENV_VAR, "$"))
    assert loader_root_dir.resolved_path is not None
    assert loader_root_dir.resolved_path.is_absolute()

    # Create test data in the resolved loader root dir
    relative_data_path = f"{test_ini_option_data_loader_root_dir.__name__}.txt"
    create_test_data_in_data_dir(
        test_context.pytester,
        DEFAULT_LOADER_DIR_NAME,
        relative_data_path,
        loader_root_dir=loader_root_dir.resolved_path,
        data=test_context.test_file_content,
    )

    ini_filedata = f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_ROOT_DIR} = {loader_root_dir.requested_path}
    """
    test_context.pytester.makefile(".ini", pytest=ini_filedata)

    result = run_pytest_with_context(
        test_context,
        path=relative_data_path,
        data_loader_root_dir=loader_root_dir.resolved_path,
        collect_only=collect_only,
    )
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
@pytest.mark.parametrize("invalid_dir_name", ["", ".", "..", ROOT_DIR, f"{ROOT_DIR}foo", f"foo{os.sep}bar"])
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
@pytest.mark.parametrize("invalid_dir", ["foo", f"{ROOT_DIR}foo", ".", f"..{os.sep}foo", ENV_VAR, __file__])
def test_ini_option_data_loader_root_dir_invalid(
    test_context: TestContext, collect_only: bool, invalid_dir: str
) -> None:
    """Test data_loader_root_dir INI option with invalid names"""
    test_context.pytester.makeini(f"""
    [pytest]
    {DataLoaderIniOption.DATA_LOADER_ROOT_DIR} = {invalid_dir}
    """)
    result = run_pytest_with_context(test_context, collect_only=collect_only)
    assert result.ret == ExitCode.USAGE_ERROR
    assert f"INI option {DataLoaderIniOption.DATA_LOADER_ROOT_DIR}: " in str(result.stderr)


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
