import pytest
from _pytest.config import ExitCode

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.types import DataLoader
from tests.tests_plugin.helper import TestContext, run_pytest_with_context

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
@pytest.mark.parametrize("id", [None, "foo"])
@pytest.mark.parametrize("loader", [load])
def test_id_for_load_loader(loader: DataLoader, test_context: TestContext, id: str | None, is_abs_path: bool) -> None:
    """Check test ID generation for load loader"""
    result = run_pytest_with_context(test_context, id_=id, check_test_id=True)
    assert result.ret == ExitCode.OK


@pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
@pytest.mark.parametrize("lazy_loading", [False, True])
@pytest.mark.parametrize("with_id_func", [False, True])
@pytest.mark.parametrize("file_extension", [".txt", ".json"])
@pytest.mark.parametrize("loader", [parametrize])
def test_id_for_parametrize_loader(
    loader: DataLoader,
    test_context: TestContext,
    lazy_loading: bool,
    with_id_func: bool,
    file_extension: str,
    is_abs_path: bool,
) -> None:
    """Check test ID generation for load parametrize loader

    NOTE: When lazy loading, the code path for generating ID with id_func changes whether the file reading is
          streamable (eg. .txt) or not (eg. .json)
    """
    id_func_def = "lambda x: f'id_{x}'" if with_id_func else None
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, id_func_def=id_func_def, check_test_id=True
    )
    assert result.ret == ExitCode.OK


@pytest.mark.parametrize("is_abs_path", [False, True], indirect=True)
@pytest.mark.parametrize("loader", [parametrize_dir])
def test_id_for_parametrize_dir_loader(loader: DataLoader, test_context: TestContext, is_abs_path: bool) -> None:
    """Check test ID generation for load parametrize_dir"""
    result = run_pytest_with_context(test_context, check_test_id=True)
    assert result.ret == ExitCode.OK
