import os
import sys

import pytest
from pytest import ExitCode

from pytest_data_loader import load
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME, ROOT_DIR
from pytest_data_loader.types import DataLoader, DataLoaderIniOption, DataLoaderOnMissingAction

from .helper import LoaderRootDir, TestContext, create_test_data_in_data_dir, run_pytest_with_context

pytestmark = pytest.mark.plugin


if sys.platform == "win32":
    ENV_VAR = "%FOO%"
else:
    ENV_VAR = "${FOO}"


class TestIniOptions:
    """Tests for pytest INI options for the data loader plugin."""

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("data_dir_name", [DEFAULT_LOADER_DIR_NAME, "new_dir", ".test"], indirect=True)
    def test_ini_option_data_loader_dir_name(
        self, test_context: TestContext, collect_only: bool, data_dir_name: str
    ) -> None:
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
        self, loader: DataLoader, test_context: TestContext, collect_only: bool, loader_root_dir: LoaderRootDir
    ) -> None:
        """Test data_loader_root_dir INI option with valid names"""
        assert loader_root_dir.requested_path is not None
        assert loader_root_dir.requested_path.startswith(("..", ENV_VAR, "$"))
        assert loader_root_dir.resolved_path is not None
        assert loader_root_dir.resolved_path.is_absolute()

        # Create test data in the resolved loader root dir
        relative_data_path = f"{self.test_ini_option_data_loader_root_dir.__name__}.txt"
        create_test_data_in_data_dir(
            test_context.pytester,
            DEFAULT_LOADER_DIR_NAME,
            relative_data_path,
            loader_root_dir=loader_root_dir.resolved_path,
            data=test_context.test_file_content,
        )

        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ROOT_DIR} = {loader_root_dir.requested_path}
        """)

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
        self, test_context: TestContext, collect_only: bool, strip_trailing_whitespace: str
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
    @pytest.mark.parametrize("on_missing", DataLoaderOnMissingAction)
    def test_ini_option_data_loader_on_missing(
        self, test_context: TestContext, collect_only: bool, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test data_loader_on_missing INI option with valid values"""
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        result = run_pytest_with_context(test_context, collect_only=collect_only)
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("default_encoding", ["utf-8", "latin-1", "ascii"])
    def test_ini_option_data_loader_default_encoding(
        self, test_context: TestContext, collect_only: bool, default_encoding: str
    ) -> None:
        """Test data_loader_default_encoding INI option with valid values"""
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_DEFAULT_ENCODING} = {default_encoding}
        """)
        result = run_pytest_with_context(test_context, collect_only=collect_only)
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)

    def test_ini_option_data_loader_default_encoding_loads_non_utf8_file(self, pytester: pytest.Pytester) -> None:
        """Test that data_loader_default_encoding enables loading a non-UTF-8 file as text."""
        encoding = "latin-1"
        latin1_text = "café\ncrème\nbrûlée\n"
        data_dir = pytester.mkdir("data")
        data_file = data_dir / "latin1.txt"
        data_file.write_bytes(latin1_text.encode(encoding))

        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_DEFAULT_ENCODING} = {encoding}
        """)
        pytester.makepyfile(f"""
        from pytest_data_loader import load

        @load("data", {str(data_file.name)!r})
        def test_latin1(data):
            assert isinstance(data, str)
            assert data == {latin1_text.rstrip()!r}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("invalid_value", ["", "not-a-codec", "utf8x", "base64", "hex"])
    def test_ini_option_data_loader_default_encoding_invalid(
        self, test_context: TestContext, collect_only: bool, invalid_value: str
    ) -> None:
        """Test data_loader_default_encoding INI option with invalid values"""
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_DEFAULT_ENCODING} = {invalid_value}
        """)
        result = run_pytest_with_context(test_context, collect_only=collect_only)
        assert result.ret == ExitCode.USAGE_ERROR
        assert (
            f"INI option {DataLoaderIniOption.DATA_LOADER_DEFAULT_ENCODING}: Invalid value: '{invalid_value}'"
            in str(result.stderr)
        )

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("invalid_dir_name", ["", ".", "..", ROOT_DIR, f"{ROOT_DIR}foo", f"foo{os.sep}bar"])
    def test_ini_option_data_loader_dir_name_invalid(
        self, test_context: TestContext, collect_only: bool, invalid_dir_name: str
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
        self, test_context: TestContext, collect_only: bool, invalid_dir: str
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
        self, test_context: TestContext, collect_only: bool, invalid_value: str
    ) -> None:
        """Test data_loader_strip_trailing_whitespace INI option with invalid values"""
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE} = {invalid_value}
        """)
        result = run_pytest_with_context(test_context, collect_only=collect_only)
        assert result.ret == ExitCode.USAGE_ERROR
        expected = (
            f"INI option {DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE}: "
            f"invalid truth value '{invalid_value}'"
        )
        assert expected in str(result.stderr)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("invalid_value", ["", "foo", "RAISE", "Skip"])
    def test_ini_option_data_loader_on_missing_invalid(
        self, test_context: TestContext, collect_only: bool, invalid_value: str
    ) -> None:
        """Test data_loader_on_missing INI option with invalid values"""
        test_context.pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {invalid_value}
        """)
        result = run_pytest_with_context(test_context, collect_only=collect_only)
        assert result.ret == ExitCode.USAGE_ERROR
        assert f"INI option {DataLoaderIniOption.DATA_LOADER_ON_MISSING}: Invalid value: '{invalid_value}'" in str(
            result.stderr
        )
