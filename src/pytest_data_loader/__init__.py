from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pytest-data-loader")
except PackageNotFoundError:
    pass


from pytest_data_loader.loaders import load, parametrize, parametrize_dir
