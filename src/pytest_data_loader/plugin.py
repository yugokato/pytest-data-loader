import logging
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

import pytest
from _pytest.fixtures import SubRequest
from _pytest.mark import ParameterSet
from pytest import Config, Mark, MarkDecorator, Metafunc, Parser

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME, PYTEST_DATA_LOADER_ATTRS, STASH_KEY_DATA_LOADER_OPTION
from pytest_data_loader.fixtures import _pytest_data_loader_cleanup, data_loader  # noqa: F401
from pytest_data_loader.loaders.impl import create_loaders
from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
)
from pytest_data_loader.utils import add_error_note, get_data_loader_source

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

    for idx, load_attrs in enumerate(reversed(load_attrs_list)):
        try:
            _apply_load_attrs(metafunc, load_attrs, data_loader_option)
        except Exception as e:
            decorator_src = get_data_loader_source(test_func, idx, load_attrs.loader.__name__)
            if decorator_src is None:
                decorator_src = f"@{load_attrs.loader.__name__}"
            add_error_note(e, f"- nodeid: {node_id}")
            add_error_note(e, f"- data loader: {decorator_src}")
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
        for loader in create_loaders(path, load_attrs, data_loader_option):
            loader.register_cleanup(metafunc.module)

            loaded = loader.load()
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
        values = (_generate_parameterset(load_attrs, x) for x in loaded_data)
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


def _generate_parameterset(
    load_attrs: DataLoaderLoadAttrs, loaded_data: LoadedData | LazyLoadedData | LazyLoadedPartData
) -> ParameterSet:
    """Generate Pytest ParameterSet object for the loaded data.

    :param load_attrs: The load attributes
    :param loaded_data: The loaded data
    """

    def generate_param_id() -> Any:
        if load_attrs.id_func is None:
            if load_attrs.lazy_loading or not (
                load_attrs.loader.is_file_loader and load_attrs.loader.requires_parametrization
            ):
                return repr(loaded_data)
            else:
                return repr(loaded_data.data)
        else:
            if isinstance(loaded_data, LazyLoadedPartData):
                # When id_func is provided for the @parametrize loader, parameter ID is generated when
                # LazyLoadedPartData is created
                return loaded_data.meta["id"] or repr(loaded_data)
            return load_attrs.id_func(loaded_data.file_path, loaded_data.data)

    def generate_param_marks() -> MarkDecorator | Collection[MarkDecorator | Mark]:
        default_markers: tuple[()] = ()
        if load_attrs.marker_func is None:
            return default_markers
        else:
            if isinstance(loaded_data, LazyLoadedPartData):
                # When marker_func is provided for the @parametrize loader, marks are generated when
                # LazyLoadedPartData is created
                marks = loaded_data.meta["marks"]
            else:
                func_args: tuple[Any, ...]
                if load_attrs.loader.is_file_loader:
                    func_args = (loaded_data.file_path, loaded_data.data)
                else:
                    func_args = (loaded_data.file_path,)
                marks = load_attrs.marker_func(*func_args)
            return marks or default_markers

    args: tuple[Any, ...]
    if load_attrs.requires_file_path:
        args = (loaded_data.file_path, loaded_data.data)
    else:
        args = (loaded_data.data,)
    try:
        return pytest.param(*args, marks=generate_param_marks(), id=generate_param_id())
    finally:
        if isinstance(loaded_data, LazyLoadedPartData):
            loaded_data.meta.clear()
