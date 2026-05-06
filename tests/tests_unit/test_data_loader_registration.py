from typing import cast

import pytest

from pytest_data_loader.loaders.loaders import loader
from pytest_data_loader.types import DataLoader, DataLoaderType

pytestmark = pytest.mark.unittest


class TestDataLoaderRegistration:
    """Tests for loader registration using the @loader decorator."""

    @pytest.mark.parametrize("loader_type", DataLoaderType)
    def test_data_loader_registration(self, loader_type: DataLoaderType) -> None:
        """Test that @loader stamps the expected attributes derived from the function name"""

        def new_loader() -> None: ...

        new_loader.__name__ = loader_type.value
        decorated = cast(DataLoader, loader(new_loader))

        assert decorated.is_data_loader is True
        assert decorated.type is loader_type
        assert decorated.is_file_loader is (loader_type in (DataLoaderType.LOAD, DataLoaderType.PARAMETRIZE))
        assert decorated.requires_parametrization is (
            loader_type in (DataLoaderType.PARAMETRIZE, DataLoaderType.PARAMETRIZE_DIR)
        )
        assert decorated.should_split_data is (loader_type is DataLoaderType.PARAMETRIZE)

    def test_data_loader_registration_invalid_name(self) -> None:
        """Test that @loader rejects a function whose name is not a valid DataLoaderType"""

        def not_a_loader() -> None: ...

        with pytest.raises(ValueError):
            loader(not_a_loader)
