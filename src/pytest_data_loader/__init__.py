from importlib.metadata import PackageNotFoundError, version

from pytest_data_loader.fixtures import DataLoaderFixture, data_loader, make_data_loader_fixture
from pytest_data_loader.loaders import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.reader import register_reader

try:
    __version__ = version("pytest-data-loader")
except PackageNotFoundError:
    pass

__all__ = [
    "DataLoaderFixture",
    "data_loader",
    "load",
    "make_data_loader_fixture",
    "parametrize",
    "parametrize_dir",
    "register_reader",
]
