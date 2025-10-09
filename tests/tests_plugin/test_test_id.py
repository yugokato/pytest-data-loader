import pytest
from _pytest.config import ExitCode

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.types import DataLoader
from tests.tests_plugin.helper import TestContext, run_pytest_with_context


@pytest.mark.parametrize("id", [None, "foo"])
@pytest.mark.parametrize("loader", [load])
def test_id_for_load_loader(loader: DataLoader, test_context: TestContext, id: str | None) -> None:
    """Check test ID generation for load loader"""
    result = run_pytest_with_context(test_context, id_=id, check_test_id=True)
    assert result.ret == ExitCode.OK


@pytest.mark.parametrize("lazy_loading", [False, True])
@pytest.mark.parametrize("with_id_func", [False, True])
@pytest.mark.parametrize("loader", [parametrize])
def test_id_for_parametrize_loader(
    loader: DataLoader, test_context: TestContext, lazy_loading: bool, with_id_func: bool
) -> None:
    """Check test ID generation for load parametrize loader"""
    id_func_def = "lambda x:x" if with_id_func else None
    result = run_pytest_with_context(
        test_context, lazy_loading=lazy_loading, id_func_def=id_func_def, check_test_id=True
    )
    if lazy_loading and with_id_func:
        assert result.ret == ExitCode.INTERRUPTED
        assert f"@{loader.__name__} loader does not support id_func when lazy_loading=True" in str(result.stdout)
    else:
        assert result.ret == ExitCode.OK


@pytest.mark.parametrize("loader", [parametrize_dir])
def test_id_for_parametrize_dir_loader(loader: DataLoader, test_context: TestContext) -> None:
    """Check test ID generation for load parametrize_dir"""
    result = run_pytest_with_context(test_context, check_test_id=True)
    assert result.ret == ExitCode.OK
