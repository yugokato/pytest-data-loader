import pytest
from pytest import ExitCode

from tests.tests_plugin.helper import TestContext, is_valid_fixture_names, run_pytest_with_context

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("fixture_names", ["arg1", "  arg1", ("arg1", "arg2"), ("arg1,arg2"), ("arg1, arg2")])
def test_loader_with_valid_args(
    test_context: TestContext, fixture_names: str | tuple[str, ...], collect_only: bool
) -> None:
    """Test that a loader with valid fixture_names are handled correctly"""
    assert is_valid_fixture_names(fixture_names)
    result = run_pytest_with_context(test_context, fixture_names=fixture_names, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize(
    "fixture_names",
    [("arg1", "arg2", "arg3"), "", ("arg1", " "), ("", "arg1"), "arg1 arg2", "test%123", "123test", "@test", "def"],
)
def test_loader_with_invalid_args(
    test_context: TestContext, fixture_names: str | tuple[str, ...], collect_only: bool
) -> None:
    """Test that a loader with invalid fixture_names are validated correctly"""
    assert not is_valid_fixture_names(fixture_names)
    result = run_pytest_with_context(test_context, fixture_names=fixture_names, collect_only=collect_only)
    assert result.ret == ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    assert "Invalid fixture_names value:" in str(result.stdout)
