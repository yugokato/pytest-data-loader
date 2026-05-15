import pytest
from pytest import ExitCode, RunResult

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType

from .helper import TestContext, get_num_func_args, run_pytest_with_context

pytestmark = pytest.mark.plugin


SUPPORTED_LOADERS = {
    DataLoaderFunctionType.ONLOAD_FUNC: [load, parametrize],
    DataLoaderFunctionType.PARAMETRIZER_FUNC: [parametrize],
    DataLoaderFunctionType.FILTER_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.PROCESS_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.MARKER_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.ID_FUNC: [parametrize, parametrize_dir],
    DataLoaderFunctionType.READER_FUNC: [parametrize_dir],
    DataLoaderFunctionType.READ_OPTIONS_FUNC: [parametrize_dir],
}


class TestLoaderFuncValidation:
    @pytest.mark.parametrize(
        "func_type",
        [
            DataLoaderFunctionType.ONLOAD_FUNC,
            DataLoaderFunctionType.PARAMETRIZER_FUNC,
            DataLoaderFunctionType.FILTER_FUNC,
            DataLoaderFunctionType.PROCESS_FUNC,
            DataLoaderFunctionType.READER_FUNC,
            DataLoaderFunctionType.READ_OPTIONS_FUNC,
        ],
    )
    def test_loader_func_with_non_callable(self, test_context: TestContext, func_type: DataLoaderFunctionType) -> None:
        """Test validation of loader functions that requires a callable"""
        loader = test_context.loader
        if loader not in SUPPORTED_LOADERS[func_type]:
            pytest.skip(reason="Not applicable")
        pytester = test_context.pytester
        name = func_type.public_name
        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.{loader.__name__}("data", {str(test_context.path)!r}, {name}="Not a callable")
        def test_func(data):
            ...
        """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"{name}: Must be a callable" in str(result.stdout)

    @pytest.mark.parametrize(
        ("loader", "func_type"),
        [
            (parametrize, DataLoaderFunctionType.PARAMETRIZER_FUNC),
            (parametrize_dir, DataLoaderFunctionType.READER_FUNC),
            (parametrize_dir, DataLoaderFunctionType.READ_OPTIONS_FUNC),
        ],
    )
    def test_loader_func_with_invalid_ret_val(
        self, test_context: TestContext, loader: DataLoader, func_type: DataLoaderFunctionType
    ) -> None:
        """Test validation of loader functions that are expected to return values of the specific data type"""
        pytester = test_context.pytester
        name = func_type.public_name
        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.{loader.__name__}("data", {str(test_context.path)!r}, {name}=lambda x: "Invalid retval")
        def test_func(data):
            ...
        """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        output = str(result.stdout)
        if func_type == DataLoaderFunctionType.PARAMETRIZER_FUNC:
            assert "Parametrized data must be an iterable container" in output
        elif func_type == DataLoaderFunctionType.READER_FUNC:
            assert f"{name}: Must be an iterable or a callable, but got " in output
        else:
            assert f"{name}: Must be a dict, but got " in output

    @pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
    @pytest.mark.parametrize("invalid_value", ["not-a-dict", [1, 2], 123], ids=["str", "list", "int"])
    def test_read_options_with_non_dict_type(
        self, test_context: TestContext, loader: DataLoader, invalid_value: str
    ) -> None:
        """Test that passing a non-dict, non-callable value to read_options raises a clear TypeError."""
        pytester = test_context.pytester
        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.{loader.__name__}("data", {str(test_context.path)!r}, read_options={invalid_value!r})
        def test_func(data):
            ...
        """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        output = str(result.stdout)
        if loader is parametrize_dir:
            assert "read_options: Must be a callable or a dict, but got" in output
        else:
            assert "read_options: Must be a dict, but got" in output

    @pytest.mark.parametrize("loader", [parametrize_dir])
    def test_read_options_func_with_unsupported_option(self, test_context: TestContext) -> None:
        """Test that read_options returning an unsupported option raises a clear error during collection."""
        result = run_pytest_with_context(test_context, read_options_def="lambda x: {'foo': 'var'}")
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"{DataLoaderFunctionType.READ_OPTIONS_FUNC.public_name}: Unsupported read options: foo" in str(
            result.stdout
        )

    @pytest.mark.parametrize("loader", [parametrize_dir])
    def test_read_options_func_with_invalid_mode(self, test_context: TestContext) -> None:
        """Test that read_options returning an unsupported mode raises a clear error during collection."""
        result = run_pytest_with_context(test_context, read_options_def="lambda x: {'mode': 'w'}")
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"{DataLoaderFunctionType.READ_OPTIONS_FUNC.public_name}: Invalid read mode: w" in str(result.stdout)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("loader", [parametrize])
    def test_parametrize_binary_file_with_no_custom_parametrizer_func(
        self, loader: DataLoader, test_context: TestContext, png_file_content: bytes, collect_only: bool
    ) -> None:
        """Test that @parametrize loader properly blocks binary data when a custom parametrizer logic is not provided"""
        relative_file_path = "image.png"
        pytester = test_context.pytester
        (pytester.path / DEFAULT_LOADER_DIR_NAME / relative_file_path).write_bytes(png_file_content)
        result = run_pytest_with_context(test_context, path=relative_file_path, collect_only=collect_only)
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"@{loader.__name__} loader requires a custom parametrizer function for binary data" in str(
            result.stdout
        )


class TestLoaderFuncArgValidation:
    """Tests for loader function argument validation."""

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:x", True, id="1arg"),
            pytest.param("lambda x,y:y", True, id="2args"),
            pytest.param("lambda x,y,z:y", False, id="3args"),
            pytest.param("lambda:True", False, id="0arg"),
            pytest.param("lambda *args:args[-1]", True, id="*args"),
            pytest.param("lambda x,*args:args[-1]", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,*_:y", False, id="3args+*args"),
            pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.ONLOAD_FUNC])
    def test_onload_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the onload parameter"""
        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, onload_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            _validate_arg_error(result, DataLoaderFunctionType.ONLOAD_FUNC, loader_func_def, 2)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:[x]", True, id="1arg"),
            pytest.param("lambda x,y:[y]", True, id="2args"),
            pytest.param("lambda x,y,z:[y]", False, id="3args"),
            pytest.param("lambda:[True]", False, id="0arg"),
            pytest.param("lambda *_:['x']", True, id="*args"),
            pytest.param("lambda x,*_:['x']", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,*_:['x']", False, id="3args+*args"),
            pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.PARAMETRIZER_FUNC])
    def test_parametrizer_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the parametrizer parameter"""
        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, parametrizer_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=1)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            _validate_arg_error(result, DataLoaderFunctionType.PARAMETRIZER_FUNC, loader_func_def, 2)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:True", True, id="1arg"),
            pytest.param("lambda x,y:True", True, id="2args"),  # for parametrize
            pytest.param("lambda x,y:True", False, id="2args"),  # for parametrize_dir
            pytest.param("lambda x,y,z:True", False, id="3args"),
            pytest.param("lambda:True", False, id="0arg"),
            pytest.param("lambda *_:True", True, id="*args"),
            pytest.param("lambda x,*_:True", True, id="1arg+*args"),
            pytest.param("lambda x,y,*_:True", True, id="2args+*args"),  # for parametrize
            pytest.param("lambda x,y,*_:True", False, id="2args+*args"),  # for parametrize_dir
            pytest.param("lambda x,y,z,*_:True", False, id="3args+*args"),
            pytest.param("lambda **kwargs:True", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.FILTER_FUNC])
    def test_filter_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the filter parameter"""

        loader_func = eval(loader_func_def)
        if callable(loader_func):
            num_args = get_num_func_args(loader_func)
            if num_args == 2:
                if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                    pytest.skip("Not applicable")

        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, filter_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            max_allowed = 1 if loader == parametrize_dir else 2
            _validate_arg_error(result, DataLoaderFunctionType.FILTER_FUNC, loader_func_def, max_allowed)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:x", True, id="1arg"),
            pytest.param("lambda x,y:y", True, id="2args"),
            pytest.param("lambda x,y,z:z", True, id="3args"),
            pytest.param("lambda:True", False, id="0arg"),
            pytest.param("lambda *_:'x'", True, id="*args"),
            pytest.param("lambda x,*_:'x'", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,w,*_:'x'", False, id="4args+*args"),
            pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.PROCESS_FUNC])
    def test_processor_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the processor parameter

        NOTE: If lazy loading is enabled, the test collection will never fail because the loader function will
              not be called until after the data is actually loaded
        """
        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, processor_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            _validate_arg_error(result, DataLoaderFunctionType.PROCESS_FUNC, loader_func_def, 3)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:pytest.mark.foo", True, id="1arg"),
            pytest.param("lambda x,y:pytest.mark.foo", True, id="2args"),
            pytest.param("lambda x,y,z:pytest.mark.foo", True, id="3args"),  # for parametrize
            pytest.param("lambda x,y,z:pytest.mark.foo", False, id="3args"),  # for parametrize_dir
            pytest.param("lambda:pytest.mark.foo", False, id="0arg"),
            pytest.param("lambda *_:pytest.mark.foo", True, id="*args"),
            pytest.param("lambda x,*_:pytest.mark.foo", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,*_:pytest.mark.foo", True, id="3args+*args"),  # for parametrize
            pytest.param("lambda x,y,z,*_:pytest.mark.foo", False, id="3args+*args"),  # for parametrize_dir
            pytest.param("lambda x,y,z,w,*_:pytest.mark.foo", False, id="4args+*args"),
            pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.MARKER_FUNC])
    def test_marks_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the marks parameter"""
        loader_func = eval(loader_func_def)
        num_args = get_num_func_args(loader_func)
        if num_args == 3:
            if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                pytest.skip("Not applicable")

        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, marks_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            max_allowed = 2 if loader == parametrize_dir else 3
            _validate_arg_error(result, DataLoaderFunctionType.MARKER_FUNC, loader_func_def, max_allowed)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:x", True, id="1arg"),
            pytest.param("lambda x,y:y", True, id="2args"),
            pytest.param("lambda x,y,z:'id'", True, id="3args"),  # for parametrize
            pytest.param("lambda x,y,z:'id'", False, id="3args"),  # for parametrize_dir
            pytest.param("lambda:True", False, id="0arg"),
            pytest.param("lambda *_:'myid'", True, id="*args"),
            pytest.param("lambda x,y,z,*_:'myid'", True, id="3args+*args"),  # for parametrize
            pytest.param("lambda x,y,z,*_:'myid'", False, id="3args+*args"),  # for parametrize_dir
            pytest.param("lambda x,y,z,w,*_:'myid'", False, id="4args+*args"),
            pytest.param("lambda **kwargs:kwargs", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.ID_FUNC])
    def test_ids_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the ids parameter"""
        loader_func = eval(loader_func_def)
        num_args = get_num_func_args(loader_func)
        if num_args == 1 and is_valid and loader == parametrize_dir:
            # For parametrize_dir, ids receives a file path; lambda x:x returns a Path object which
            # is not a valid pytest ID string. Valid runtime behavior is covered by integration tests.
            pytest.skip("Not applicable")
        elif num_args == 2 and is_valid and loader == parametrize_dir:
            # For parametrize_dir with 2-arg ids, the callable receives (idx, file_path);
            # lambda x,y:y returns a Path which is not a valid pytest ID string.
            pytest.skip("Not applicable")
        elif num_args == 3:
            if (loader == parametrize and not is_valid) or (loader == parametrize_dir and is_valid):
                pytest.skip("Not applicable")

        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, ids_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            max_allowed = 2 if loader == parametrize_dir else 3
            _validate_arg_error(result, DataLoaderFunctionType.ID_FUNC, loader_func_def, max_allowed)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:{}", True, id="1arg"),
            pytest.param("lambda x,y:{}", True, id="2args"),
            pytest.param("lambda x,y,z:{}", False, id="3args"),
            pytest.param("lambda:{}", False, id="0arg"),
            pytest.param("lambda *_:{}", True, id="*args"),
            pytest.param("lambda x,*_:{}", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,*_:{}", False, id="3args+*args"),
            pytest.param("lambda **kwargs:{}", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.READ_OPTIONS_FUNC])
    def test_read_options_func_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the read_options parameter"""
        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, read_options_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            _validate_arg_error(result, DataLoaderFunctionType.READ_OPTIONS_FUNC, loader_func_def, 2)

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize(
        ("loader_func_def", "is_valid"),
        [
            pytest.param("lambda x:json.load", True, id="1arg"),
            pytest.param("lambda x,y:json.load", True, id="2args"),
            pytest.param("lambda x,y,z:json.load", False, id="3args"),
            pytest.param("lambda:json.load", False, id="0arg"),
            pytest.param("lambda *_:json.load", True, id="*args"),
            pytest.param("lambda x,*_:json.load", True, id="1arg+*args"),
            pytest.param("lambda x,y,z,*_:json.load", False, id="3args+*args"),
            pytest.param("lambda **kwargs:json.load", False, id="**kwargs"),
        ],
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("file_extension", [".json"], indirect=True)
    @pytest.mark.parametrize("loader", SUPPORTED_LOADERS[DataLoaderFunctionType.READER_FUNC])
    def test_reader_validation(
        self,
        test_context: TestContext,
        loader: DataLoader,
        loader_func_def: str,
        file_extension: str,
        is_valid: bool,
        lazy_loading: bool,
        collect_only: bool,
    ) -> None:
        """Test validation around the reader parameter"""
        result = run_pytest_with_context(
            test_context, lazy_loading=lazy_loading, reader_def=loader_func_def, collect_only=collect_only
        )
        if is_valid:
            assert result.ret == ExitCode.OK
            if not collect_only:
                result.assert_outcomes(passed=test_context.num_expected_tests)
        else:
            assert result.ret == ExitCode.INTERRUPTED
            result.assert_outcomes(errors=1)
            _validate_arg_error(result, DataLoaderFunctionType.READER_FUNC, loader_func_def, 2)


def _validate_arg_error(
    result: RunResult, func_type: DataLoaderFunctionType, func_def: str, max_allowed_args: int
) -> None:
    err = f"Detected invalid '{func_type.public_name}' callable definition."
    output = str(result.stdout)
    if "**" in func_def:
        assert f"{err} Only positional arguments are allowed" in output
    else:
        if max_allowed_args == 1:
            assert f"{err} It must take only 1 argument (file path)" in output
        else:
            assert f"{err} It must take up to {max_allowed_args} arguments" in output
