import pytest
from _pytest.config import ExitCode

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType, DataLoaderIniOption, DataLoaderOnMissingAction

from .helper import TestContext, run_pytest_with_context

pytestmark = pytest.mark.plugin


class TestParamId:
    """Tests for test ID generation across different loaders."""

    @pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
    @pytest.mark.parametrize("id", ["foo", None])
    @pytest.mark.parametrize("loader", [load])
    def test_id_generation_for_load_loader(
        self, loader: DataLoader, test_context: TestContext, id: str | None, is_abs_path: bool
    ) -> None:
        """Check test ID generation for load loader"""
        result = run_pytest_with_context(test_context, id_=id, check_test_id=True)
        assert result.ret == ExitCode.OK

    @pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
    @pytest.mark.parametrize("lazy_loading", [False, True])
    @pytest.mark.parametrize("value_type", ["callable", "sequence", "generator", None])
    @pytest.mark.parametrize("file_extension", [".txt", ".yml"])
    @pytest.mark.parametrize("loader", [parametrize])
    def test_id_generation_for_parametrize_loader(
        self,
        loader: DataLoader,
        test_context: TestContext,
        lazy_loading: bool,
        value_type: str | None,
        file_extension: str,
        is_abs_path: bool,
    ) -> None:
        """Check test ID generation for load parametrize loader

        NOTE: When lazy loading, the code path for generating ID with id_func changes whether the file reading is
              streamable (eg. .txt) or not (eg. .yml)
        """
        if value_type == "callable":
            ids_def = "lambda x: f'id-{x}'"
        elif value_type == "sequence":
            ids_def = f"[f'id={{i}}' for i in range({test_context.num_expected_tests})]"
        elif value_type == "generator":
            ids_def = f"(f'id={{i}}' for i in range({test_context.num_expected_tests}))"
        else:
            ids_def = None
        result = run_pytest_with_context(test_context, lazy_loading=lazy_loading, ids_def=ids_def, check_test_id=True)
        assert result.ret == ExitCode.OK

    @pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
    @pytest.mark.parametrize("lazy_loading", [False, True])
    @pytest.mark.parametrize("value_type", ["callable", "sequence", "generator", None])
    @pytest.mark.parametrize("loader", [parametrize_dir])
    def test_id_generation_for_parametrize_dir_loader(
        self,
        loader: DataLoader,
        test_context: TestContext,
        is_abs_path: bool,
        lazy_loading: bool,
        value_type: str | None,
    ) -> None:
        """Check test ID generation for parametrize_dir loader with and without id_func"""
        if value_type == "callable":
            ids_def = "lambda x: f'id-{x}'"
        elif value_type == "sequence":
            ids_def = f"[f'id={{i}}' for i in range({test_context.num_expected_tests})]"
        elif value_type == "generator":
            ids_def = f"(f'id={{i}}' for i in range({test_context.num_expected_tests}))"
        else:
            ids_def = None
        result = run_pytest_with_context(test_context, lazy_loading=lazy_loading, ids_def=ids_def, check_test_id=True)
        assert result.ret == ExitCode.OK

    @pytest.mark.parametrize("loader", [parametrize, parametrize_dir])
    def test_id_generation_with_invalid_value(self, test_context: TestContext) -> None:
        """Test that a non-iterable, non-callable ids value raises a clear error."""
        result = run_pytest_with_context(test_context, ids_def="123")
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"{DataLoaderFunctionType.ID_FUNC.public_name}: Must be a callable or an iterable" in str(result.stdout)

    @pytest.mark.parametrize("loader", [parametrize, parametrize_dir])
    def test_id_generation_with_empty_ids(self, test_context: TestContext) -> None:
        """Test that an empty ids should be handled gracefully"""
        result = run_pytest_with_context(test_context, ids_def="[]")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=test_context.num_expected_tests)

    @pytest.mark.parametrize("scenario", ["short", "long"])
    @pytest.mark.parametrize("loader", [parametrize, parametrize_dir])
    def test_id_generation_with_mismatched_length(self, test_context: TestContext, scenario: str) -> None:
        """Test that an ids sequence shorter or longer than the number of parametrized cases raises a clear error"""
        num_tests = test_context.num_expected_tests
        valid_ids = [f"id-{i}" for i in range(num_tests)]
        if scenario == "short":
            invalid_ids = valid_ids[:-1]
        else:
            invalid_ids = [*valid_ids, "extra"]
        result = run_pytest_with_context(test_context, ids_def=f"{invalid_ids}")
        assert result.ret == ExitCode.INTERRUPTED
        result.assert_outcomes(errors=1)
        assert f"ids: Length ({len(invalid_ids)}) does not match number of parameter sets ({num_tests})" in str(
            result.stdout
        )


class TestParamIdOnMissingData:
    """Tests for id_func and idx correctness when on_missing != raise."""

    @pytest.mark.parametrize(
        "on_missing",
        [DataLoaderOnMissingAction.SKIP, DataLoaderOnMissingAction.XFAIL, DataLoaderOnMissingAction.WARN],
    )
    def test_ids_callable_ignored_on_missing(
        self, pytester: pytest.Pytester, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test that a user-supplied ids callable is not invoked for a missing path."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/present": "hello"})
        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("data", ["present.txt", "absent.txt"], ids=lambda p, d: "custom-" + str(d))
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("-v")
        output = str(result.stdout)
        assert "custom-None" not in output
        result.stdout.fnmatch_lines("*absent.txt:MISSING*")
