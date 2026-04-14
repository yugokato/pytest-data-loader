import logging
from collections.abc import Generator, Iterable
from pathlib import Path
from typing import cast

import pytest
from _pytest.fixtures import SubRequest
from pytest import Config, Metafunc, Parser, StashKey

from pytest_data_loader.constants import (
    DEFAULT_LOADER_DIR_NAME,
    PYTEST_DATA_LOADER_ATTRS,
    PYTEST_DATA_LOADER_MODULE_CACHE,
)
from pytest_data_loader.loaders.impl import (
    DirectoryDataLoader,
    FileDataLoader,
    data_loader_factory,
    resolve_relative_path,
)
from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
)
from pytest_data_loader.utils import add_error_note, generate_parameterset

STASH_KEY_DATA_LOADER_OPTION = StashKey[DataLoaderOption]()
logger = logging.getLogger(__name__)


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
    load_attrs_list: list[DataLoaderLoadAttrs] | None = getattr(test_func, PYTEST_DATA_LOADER_ATTRS, None)
    if not load_attrs_list:
        return

    node_id = metafunc.definition.nodeid
    data_loader_option = metafunc.config.stash[STASH_KEY_DATA_LOADER_OPTION]

    for idx, load_attrs in enumerate(reversed(load_attrs_list), start=1):
        try:
            _apply_load_attrs(metafunc, load_attrs, data_loader_option)
        except Exception as e:
            add_error_note(
                e,
                f"Location: {node_id}@{load_attrs.loader.__name__}(fixture_names={load_attrs.fixture_names}, "
                f"path={str(load_attrs.path)!r})",
            )
            raise


def _apply_load_attrs(
    metafunc: Metafunc, load_attrs: DataLoaderLoadAttrs, data_loader_option: DataLoaderOption
) -> None:
    """Apply a single DataLoaderLoadAttrs entry to metafunc, calling metafunc.parametrize once

    :param metafunc: The pytest Metafunc object for the current test function
    :param load_attrs: A single DataLoaderLoadAttrs describing one stacked decorator's configuration
    :param data_loader_option: Data loader options
    """
    paths = load_attrs.path if isinstance(load_attrs.path, tuple) else (load_attrs.path,)
    loaded_data: list[LoadedData | LazyLoadedData | LazyLoadedPartData] = []

    for path in paths:
        if path.is_absolute():
            data_dir_path = None
            test_data_path = path
        else:
            data_dir_path, test_data_path = resolve_relative_path(
                data_loader_option.loader_dir_name,
                data_loader_option.loader_root_dir,
                path,
                load_attrs.search_from,
                is_file=load_attrs.loader.is_file_loader,
            )

        data_loader = data_loader_factory(
            test_data_path,
            load_attrs,
            load_from=data_dir_path,
            strip_trailing_whitespace=cast(bool, data_loader_option.strip_trailing_whitespace),
        )

        # Keep file/directory loaders per module for clean up
        data_loader_cache: set[FileDataLoader | DirectoryDataLoader] | None
        if data_loader_cache := getattr(metafunc.module, PYTEST_DATA_LOADER_MODULE_CACHE, None):
            data_loader_cache.add(data_loader)
        else:
            setattr(metafunc.module, PYTEST_DATA_LOADER_MODULE_CACHE, {data_loader})

        loaded = data_loader.load()
        if isinstance(loaded, LoadedData | LazyLoadedData):
            loaded_data.append(loaded)
        elif loaded:
            loaded_data.extend(loaded)

    values: Iterable[
        LoadedDataType
        | LazyLoadedData
        | LazyLoadedPartData
        | tuple[Path, LoadedDataType | LazyLoadedData | LazyLoadedPartData]
    ]
    if loaded_data:
        values = (generate_parameterset(load_attrs, x) for x in loaded_data)
    else:
        values = []

    args: str | tuple[str, ...]
    if len(load_attrs.fixture_names) == 1:
        args = load_attrs.fixture_names[0]
    else:
        args = load_attrs.fixture_names
    metafunc.parametrize(args, values)


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(request: SubRequest) -> None:
    """Resolve lazily loaded data to actual data"""
    val = getattr(request, "param", None)
    if isinstance(val, LazyLoadedData | LazyLoadedPartData):
        request.param = val.resolve()


@pytest.fixture(scope="module", autouse=True)
def _pytest_data_loader_cleanup(request: SubRequest) -> Generator[None]:
    """Clear cache used by data loaders with lazy loading at the end of each module"""
    yield
    data_loaders: set[FileDataLoader | DirectoryDataLoader] | None
    if data_loaders := getattr(request.module, PYTEST_DATA_LOADER_MODULE_CACHE, None):
        for data_loader in data_loaders:
            try:
                data_loader.clear_cache()
            except Exception as e:
                logger.exception(e)
        data_loaders.clear()
