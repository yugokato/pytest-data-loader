from typing import Any

import pytest

from pytest_data_loader import make_data_loader_fixture

pytestmark = pytest.mark.unittest


class TestMakeDataLoaderFixture:
    """Tests for make_data_loader_fixture()."""

    @pytest.mark.parametrize("scope", ["", "invalid", "Session", None, 1])
    def test_make_data_loader_fixture_raises_for_invalid_scope(self, scope: Any) -> None:
        """Test that an invalid scope is rejected with an error that lists the valid scopes."""
        with pytest.raises(ValueError, match=r"scope: Must be one of function, class, module, package, session"):
            make_data_loader_fixture(scope)
