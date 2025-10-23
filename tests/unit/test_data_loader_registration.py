from typing import cast

import pytest

from pytest_data_loader.loaders.loaders import loader
from pytest_data_loader.types import DataLoader, DataLoaderType

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("parametrize", [None, False, True])
@pytest.mark.parametrize("loader_type", DataLoaderType)
def test_data_loader_registration(loader_type: DataLoaderType, parametrize: bool) -> None:
    """Test loader registration using the @loader decorator"""

    @loader(loader_type, parametrize=parametrize)
    def new_loader() -> None: ...

    is_file_loader = loader_type is DataLoaderType.FILE
    assert cast(DataLoader, new_loader).is_file_loader is is_file_loader
    assert cast(DataLoader, new_loader).requires_parametrization is (parametrize is True)
    assert cast(DataLoader, new_loader).should_split_data is bool(is_file_loader and parametrize)
