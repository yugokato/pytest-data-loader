import pytest

from pytest_data_loader.loaders.impl import loader
from pytest_data_loader.types import DataLoader, DataLoaderPathType


@pytest.mark.parametrize("parametrize", [None, False, True])
@pytest.mark.parametrize("loader_path_type", DataLoaderPathType)
def test_data_loader_registration(loader_path_type: DataLoaderPathType, parametrize) -> None:
    """Test loader registration using the @loader decorator"""

    @loader(loader_path_type, parametrize=parametrize)
    def new_loader() -> None: ...

    @loader(loader_path_type, parametrize=parametrize)
    def parametrize_new_loader() -> None: ...

    registered_loader: DataLoader
    for registered_loader in (new_loader, parametrize_new_loader):
        is_file_loader = loader_path_type is DataLoaderPathType.FILE
        assert registered_loader.requires_file_path is is_file_loader
        assert registered_loader.requires_parametrization is (parametrize is True)
