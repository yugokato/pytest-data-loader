import inspect
import sys
from collections.abc import Generator, Iterable
from pathlib import Path

import pytest
from _pytest.fixtures import SubRequest
from pytest import Config, Metafunc, Parser

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME, PYTEST_DATA_LOADER_ATTR
from pytest_data_loader.loaders.impl import FileDataLoader, data_loader_factory
from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
)
from pytest_data_loader.utils import (
    bind_and_call_loader_func,
    generate_default_id,
    parse_ini_option,
    resolve_relative_path,
)


def pytest_addoption(parser: Parser) -> None:
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_DIR_NAME,
        type="string",
        default=DEFAULT_LOADER_DIR_NAME,
        help="[pytest-data-loader] Overrides the plugin default value for data loader directory name.",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_ROOT_DIR,
        type="string",
        default="",
        help="[pytest-data-loader] Specifies the absolute or relative path to the project's actual root directory. "
        "This directory defines the upper boundary when searching for data loader directories. By default, the search "
        "is limited to within pytest's rootdir, which may differ from the project's top-level directory. Setting this "
        "option allows data loader directories located outside pytest's rootdir to be found. "
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
    parse_ini_option(config, DataLoaderIniOption.DATA_LOADER_DIR_NAME)
    parse_ini_option(config, DataLoaderIniOption.DATA_LOADER_ROOT_DIR)
    parse_ini_option(config, DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE)


def pytest_generate_tests(metafunc: Metafunc) -> None:
    test_func = metafunc.function
    load_attrs: DataLoaderLoadAttrs | None
    if load_attrs := getattr(test_func, PYTEST_DATA_LOADER_ATTR, None):
        node_id = metafunc.definition.nodeid
        try:
            cfg = metafunc.config
            data_loader_dir_name = parse_ini_option(cfg, DataLoaderIniOption.DATA_LOADER_DIR_NAME)
            data_loader_root_dir = parse_ini_option(cfg, DataLoaderIniOption.DATA_LOADER_ROOT_DIR)
            strip_trailing_whitespace = parse_ini_option(cfg, DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE)
            assert isinstance(strip_trailing_whitespace, bool)
            search_from = Path(inspect.getabsfile(test_func))
            test_data_path = resolve_relative_path(
                data_loader_dir_name,
                data_loader_root_dir,
                load_attrs.relative_path,
                search_from,
                is_file=load_attrs.loader.requires_file_path,
            )

            data_loader = data_loader_factory(
                test_data_path, load_attrs, strip_trailing_whitespace=strip_trailing_whitespace
            )
            if isinstance(data_loader, FileDataLoader):
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
                if load_attrs.requires_file_path:
                    values = ((x.file_path, x.data) for x in loaded_data)
                else:
                    values = (x.data for x in loaded_data)

                if load_attrs.id_func:
                    ids = (bind_and_call_loader_func(load_attrs.id_func, x.file_path, x.data) for x in loaded_data)
                else:
                    ids = (generate_default_id(load_attrs, x) for x in loaded_data)
            else:
                ids = None
                values = []

            if len(load_attrs.fixture_names) == 1:
                args = load_attrs.fixture_names[0]
            else:
                args = load_attrs.fixture_names
            metafunc.parametrize(args, values, ids=ids)
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
