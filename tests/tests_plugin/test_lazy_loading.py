from pathlib import Path

import pytest
from pytest import ExitCode

from pytest_data_loader import parametrize
from pytest_data_loader.types import LazyLoadedData, LazyLoadedPartData
from tests.tests_plugin.helper import TestContext, run_pytest_with_context


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("file_extension", [".txt", ".json", ".png"], indirect=True)
@pytest.mark.parametrize("lazy_loading", [False, True])
def test_lazy_loading(test_context: TestContext, lazy_loading: bool, collect_only: bool, file_extension: str) -> None:
    """Test that data is always loaded lazily when lazy loading is enabled. When lazy loading is enabled, the fixture
    setup should receive the value as either LazyLoadedData or LazyLoadedPartData
    """
    if file_extension == ".png" and test_context.loader == parametrize:
        # Not supported. The validation is tested in another test
        pytest.skip("Not applicable")

    pytester = test_context.pytester
    fixture_name = "arg1"

    if test_context.loader == parametrize:
        pytester.makeconftest(f"""
        import pytest
        from pytest_data_loader.types import LazyLoadedPartData

        @pytest.hookimpl(tryfirst=True)
        def pytest_fixture_setup(request) -> None:
            assert request.fixturename in request.fixturenames
            if request.fixturename == '{fixture_name}':
                v = request.param
                if {lazy_loading}:
                    assert isinstance(v, {LazyLoadedPartData.__name__}), (
                        f"Expected a {LazyLoadedPartData.__name__} instance, got {{type(v).__name__}}"
                    )
                    idx =  request.node.callspec.indices[request.fixturename]
                    assert request.node.name.endswith(f"[{Path(test_context.relative_path).name}:part{{idx+1}}]")
                else:
                    assert isinstance(v, type(v))
                    assert request.node.name.endswith(f"[{{repr(v)}}]")
        """)
    else:
        pytester.makeconftest(f"""
        import pytest
        from pytest_data_loader.types import LazyLoadedData

        @pytest.hookimpl(tryfirst=True)
        def pytest_fixture_setup(request) -> None:
            assert request.fixturename in request.fixturenames
            if request.fixturename == '{fixture_name}':
                v = request.param
                if {lazy_loading}:
                    assert isinstance(v, {LazyLoadedData.__name__}), (
                        f"Expected a {LazyLoadedData.__name__} instance, got {{type(v).__name__}}"
                    )
                else:
                    assert isinstance(v, type(v))
        """)

    result = run_pytest_with_context(test_context, fixture_name, lazy_loading=lazy_loading, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)
