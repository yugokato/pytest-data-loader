import pytest

from pytest_data_loader.loaders.loaders import loader
from pytest_data_loader.types import DataLoaderPathType

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("parametrize", [None, False, True])
@pytest.mark.parametrize("loader_path_type", DataLoaderPathType)
def test_data_loader_registration(loader_path_type: DataLoaderPathType, parametrize: bool) -> None:
    """Test loader registration using the @loader decorator"""

    @loader(loader_path_type, parametrize=parametrize)
    def new_loader() -> None: ...

    is_file_loader = loader_path_type is DataLoaderPathType.FILE
    assert new_loader.requires_file_path is is_file_loader
    assert new_loader.requires_parametrization is (parametrize is True)
    assert new_loader.should_split_data is bool(is_file_loader and parametrize)
