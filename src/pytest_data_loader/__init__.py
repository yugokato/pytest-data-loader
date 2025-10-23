from importlib.metadata import PackageNotFoundError, version

from pytest_data_loader.loaders import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.reader import register_reader

try:
    __version__ = version("pytest-data-loader")
except PackageNotFoundError:
    pass
