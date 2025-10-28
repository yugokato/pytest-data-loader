import sys
from collections.abc import Generator, Iterable
from pathlib import Path

import pytest
from _pytest.fixtures import SubRequest
from pytest import Config, Metafunc, Parser, StashKey

from pytest_data_loader import parametrize
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME, PYTEST_DATA_LOADER_ATTR
from pytest_data_loader.loaders.impl import FileDataLoader, data_loader_factory, resolve_relative_path
from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
)
from pytest_data_loader.utils import generate_parameterset

STASH_KEY_DATA_LOADER_OPTION = StashKey[DataLoaderOption]()


def pytest_addoption(parser: Parser) -> None:
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_DIR_NAME,
        type="string",
        default=DEFAULT_LOADER_DIR_NAME,
        help="[pytest-data-loader] The base directory name to load test data from.",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_ROOT_DIR,
        type="string",
        default="",
        help="[pytest-data-loader] Absolute or relative path to the project's root directory. This directory defines "
        "the upper boundary when searching for data directories. By default, the search is limited to within pytest's "
        "rootdir, which may differ from the project's top-level directory. Setting this option allows data directories "
        "located outside pytest's rootdir to be found. "
        "Environment variables are supported using the ${VAR} or $VAR (or %VAR% for windows) syntax.",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE,
        type="bool",
        default=True,
        help="[pytest-data-loader] Removes trailing whitespace characters when loading text data.",
    )


def pytest_configure(config: Config) -> None:
    """Parse INI options for the plugin and fail early with a nice USAGE_ERROR error if validation fails"""
    config.stash[STASH_KEY_DATA_LOADER_OPTION] = DataLoaderOption(config)


def pytest_generate_tests(metafunc: Metafunc) -> None:
    test_func = metafunc.function
    load_attrs: DataLoaderLoadAttrs | None
    if load_attrs := getattr(test_func, PYTEST_DATA_LOADER_ATTR, None):
        node_id = metafunc.definition.nodeid
        try:
            data_loader_option = metafunc.config.stash[STASH_KEY_DATA_LOADER_OPTION]
            if load_attrs.path.is_absolute():
                test_data_path = load_attrs.path
            else:
                test_data_path = resolve_relative_path(
                    data_loader_option.loader_dir_name,
                    data_loader_option.loader_root_dir,
                    load_attrs.path,
                    load_attrs.search_from,
                    is_file=load_attrs.loader.is_file_loader,
                )

            data_loader = data_loader_factory(
                test_data_path, load_attrs, strip_trailing_whitespace=data_loader_option.strip_trailing_whitespace
            )
            if load_attrs.loader == parametrize and isinstance(data_loader, FileDataLoader):
                # Keep file loaders per module for clean up
                data_loader_cache: set[FileDataLoader] | None
                if data_loader_cache := getattr(metafunc.module, PYTEST_DATA_LOADER_ATTR, None):
                    data_loader_cache.add(data_loader)
                else:
                    setattr(metafunc.module, PYTEST_DATA_LOADER_ATTR, {data_loader})

            loaded_data = data_loader.load()
            if loaded_data:
                if isinstance(loaded_data, LoadedData | LazyLoadedData):
                    loaded_data = [loaded_data]

                values: Iterable[
                    LoadedDataType
                    | LazyLoadedData
                    | LazyLoadedPartData
                    | tuple[Path, LoadedDataType | LazyLoadedData | LazyLoadedPartData]
                ]
                values = (generate_parameterset(load_attrs, x) for x in loaded_data)
            else:
                values = []

            if len(load_attrs.fixture_names) == 1:
                args = load_attrs.fixture_names[0]
            else:
                args = load_attrs.fixture_names
            metafunc.parametrize(args, values)
        except Exception as e:
            # Add nodeid to the exception message so that a user can tell which test caused the error
            note = f"(nodeid: {node_id})"
            if sys.version_info >= (3, 11):
                e.add_note(note)
                raise e
            else:
                if len(e.args) == 1 and isinstance(e.args[0], str):
                    e.args = (f"{e}\n{note}",)
                    raise e
                else:
                    raise type(e)(f"{e}\n{note}").with_traceback(e.__traceback__) from e


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(request: SubRequest) -> None:
    """Resolve lazily loaded data to actual data"""
    val = getattr(request, "param", None)
    if isinstance(val, LazyLoadedData | LazyLoadedPartData):
        request.param = val.resolve()


@pytest.fixture(scope="module", autouse=True)
def _pytest_data_loader_cleanup(request: SubRequest) -> Generator[None]:
    """Clear cache used by the @parametrize loader with lazy loading at the end of each module"""
    yield
    file_data_loaders: set[FileDataLoader] | None
    if file_data_loaders := getattr(request.module, PYTEST_DATA_LOADER_ATTR, None):
        for file_data_loader in file_data_loaders:
            file_data_loader.clear_cache()
