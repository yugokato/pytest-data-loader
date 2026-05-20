import logging
import warnings
from collections.abc import Collection, Iterable
from itertools import count
from pathlib import Path
from typing import Any, cast

import pytest
from _pytest.fixtures import SubRequest
from _pytest.mark import ParameterSet
from pytest import Config, Mark, MarkDecorator, Metafunc, Parser

from pytest_data_loader.constants import (
    DEFAULT_ENCODING,
    DEFAULT_LOADER_DIR_NAME,
    DEFAULT_MAX_CACHED_CONTENT_SIZE,
    DEFAULT_MAX_OPEN_FILE_HANDLES,
    PYTEST_DATA_LOADER_ATTRS,
    STASH_KEY_DATA_LOADER_OPTION,
    STASH_KEY_FILE_CACHE,
)
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.fixtures import _pytest_data_loader_cleanup, data_loader  # noqa: F401
from pytest_data_loader.loaders.cache import SessionFileCache
from pytest_data_loader.loaders.impl import create_loaders
from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    DataLoaderOnMissingAction,
    DataLoaderOption,
    DataLoaderType,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
    MissingData,
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
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_ON_MISSING,
        type="string",
        default=DataLoaderOnMissingAction.RAISE.value,
        help="[pytest-data-loader] The action to take when a data file or directory specified as path cannot be "
        "located. Supported values: 'raise' (default, raise an error), 'skip' (skip the test), 'xfail' "
        "(xfail the test without running it), 'warn' (emit a UserWarning and run the test with data=None).",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_DEFAULT_ENCODING,
        type="string",
        default=DEFAULT_ENCODING,
        help="[pytest-data-loader] The default text encoding to use when opening data files in text mode.",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_MAX_CACHE_SIZE,
        type="string",
        default=DEFAULT_MAX_CACHED_CONTENT_SIZE,
        help="[pytest-data-loader] Maximum total size of the session-scoped raw file content cache. Supports decimal "
        "units (KB, MB, GB, etc.) and binary units (KiB, MiB, GiB, etc.). A bare integer with no unit is interpreted "
        "as bytes. Set to 0 to disable raw-content caching.",
    )
    parser.addini(
        DataLoaderIniOption.DATA_LOADER_MAX_OPEN_FILES,
        type="string",
        default=str(DEFAULT_MAX_OPEN_FILE_HANDLES),
        help="[pytest-data-loader] Maximum number of simultaneously pooled open file handles for the "
        "session-scoped cache. Set to 0 to disable handle pooling (each loader uses a per-instance handle).",
    )


def pytest_configure(config: Config) -> None:
    """Parse INI options for the plugin and fail early with a nice USAGE_ERROR error if validation fails"""
    option = DataLoaderOption(config)
    config.stash[STASH_KEY_DATA_LOADER_OPTION] = option
    config.stash[STASH_KEY_FILE_CACHE] = SessionFileCache(
        max_content_bytes=cast(int, option.max_cache_bytes), max_open_handles=cast(int, option.max_open_files)
    )


def pytest_unconfigure(config: Config) -> None:
    """Release the session file cache (pooled handles + raw-content LRU)"""
    try:
        config.stash[STASH_KEY_FILE_CACHE].clear()
    except KeyError:
        pass


def pytest_generate_tests(metafunc: Metafunc) -> None:
    test_func = metafunc.function
    load_attrs_list: list[DataLoaderLoadAttrs] | None = getattr(test_func, PYTEST_DATA_LOADER_ATTRS, None)
    if not load_attrs_list:
        return

    node_id = metafunc.definition.nodeid
    data_loader_option = metafunc.config.stash[STASH_KEY_DATA_LOADER_OPTION]

    for idx, load_attrs in enumerate(reversed(load_attrs_list)):
        try:
            _apply_load_attrs(idx, metafunc, load_attrs, data_loader_option)
        except Exception as e:
            decorator_src = get_data_loader_source(test_func, idx, load_attrs.loader.__name__)
            if decorator_src is None:
                decorator_src = f"@{load_attrs.loader.__name__}"
            add_error_note(e, f"- nodeid: {node_id}")
            add_error_note(e, f"- data loader: {decorator_src}")
            raise


def _apply_load_attrs(
    loader_idx: int, metafunc: Metafunc, load_attrs: DataLoaderLoadAttrs, data_loader_option: DataLoaderOption
) -> None:
    """Apply a single DataLoaderLoadAttrs entry to metafunc, calling metafunc.parametrize once

    :param loader_idx: index of the data loader decorator on a test function
    :param metafunc: The pytest Metafunc object for the current test function
    :param load_attrs: A single DataLoaderLoadAttrs describing one stacked decorator's configuration
    :param data_loader_option: Data loader options
    """
    paths = load_attrs.path if isinstance(load_attrs.path, tuple) else (load_attrs.path,)
    loaded_data: list[LoadedData | LazyLoadedData | LazyLoadedPartData | MissingData] = []
    file_cache = metafunc.config.stash[STASH_KEY_FILE_CACHE]

    # One shared counter per data loader invocation. Stacked loaders each get their own independent counter
    gidx_counter = count()

    has_missing_data = False
    for path in paths:
        try:
            for loader in create_loaders(
                path, load_attrs, data_loader_option, file_cache=file_cache, gidx_counter=gidx_counter
            ):
                loader.register_cleanup(metafunc.module)

                loaded = loader.load()
                if isinstance(loaded, LoadedData | LazyLoadedData):
                    loaded_data.append(loaded)
                elif loaded:
                    loaded_data.extend(loaded)
        except DataNotFound as e:
            if data_loader_option.on_missing == DataLoaderOnMissingAction.RAISE:
                raise
            has_missing_data = True
            loaded_data.append(MissingData(file_path=path, error=e))

    ids = load_attrs.ids
    if ids is not None and len(ids) != len(loaded_data):
        if has_missing_data and len(ids) > len(loaded_data):
            # We don't know the total number of parametrization when data is missing.
            ids = ()
            msg = (
                "Ignored the provided ids value. Unable to determine the number of parametrized items due to missing "
                "data."
            )
            _emit_warning(msg, metafunc, loader_idx, load_attrs)
        else:
            raise ValueError(f"ids: Length ({len(ids)}) does not match number of parameter sets ({len(loaded_data)})")

    values: Iterable[
        LoadedDataType
        | LazyLoadedData
        | LazyLoadedPartData
        | tuple[Path, LoadedDataType | LazyLoadedData | LazyLoadedPartData]
        | None
    ]
    if data_loader_option.on_missing == DataLoaderOnMissingAction.WARN:
        for x in loaded_data:
            if isinstance(x, MissingData):
                _emit_warning(f"{type(x.error).__name__}: {x.error}", metafunc, loader_idx, load_attrs)

    if loaded_data:
        values = [
            _generate_parameterset(load_attrs, data_loader_option, x, id_=ids[i] if ids else None)
            for i, x in enumerate(loaded_data)
        ]
    else:
        values = []

    metafunc.parametrize(load_attrs.fixture_names, values)


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(request: SubRequest) -> None:
    """Resolve lazily loaded data to actual data"""
    val = getattr(request, "param", None)
    if isinstance(val, LazyLoadedData | LazyLoadedPartData):
        request.param = val.resolve()


def _generate_parameterset(
    load_attrs: DataLoaderLoadAttrs,
    data_loader_option: DataLoaderOption,
    loaded_data: LoadedData | LazyLoadedData | LazyLoadedPartData | MissingData,
    *,
    id_: Any = None,
) -> ParameterSet:
    """Generate Pytest ParameterSet object for the loaded data.

    :param load_attrs: The load attributes
    :param data_loader_option: Data loader options
    :param loaded_data: The loaded data
    :param id_: Explicit ID value from a sequence-based ids argument
    """

    def generate_param_id() -> Any:
        if id_ is not None:
            return id_

        if isinstance(loaded_data, MissingData):
            return repr(loaded_data)

        if load_attrs.id_func:
            if isinstance(loaded_data, LazyLoadedPartData):
                # When `ids` callable is provided for the @parametrize loader, parameter ID is generated when
                # LazyLoadedPartData is created
                param_id = loaded_data.meta["id"]
                if param_id is not None:
                    return param_id
                return repr(loaded_data)
            if load_attrs.loader.requires_parametrization:
                assert loaded_data.gidx is not None
                return load_attrs.id_func(loaded_data.gidx, loaded_data.file_path, loaded_data.data)
            else:
                return load_attrs.id_func(loaded_data.file_path, loaded_data.data)

        # Default ID
        if load_attrs.lazy_loading or not (load_attrs.loader.type == DataLoaderType.PARAMETRIZE):
            return repr(loaded_data)
        else:
            return repr(loaded_data.data)

    def generate_param_marks() -> MarkDecorator | Collection[MarkDecorator | Mark]:
        default_markers: tuple[()] = ()
        if isinstance(loaded_data, MissingData):
            on_missing = data_loader_option.on_missing
            reason = f"{type(loaded_data.error).__name__}: {loaded_data.error}"
            if on_missing == DataLoaderOnMissingAction.SKIP:
                marks = pytest.mark.skip(reason=reason)
            elif on_missing == DataLoaderOnMissingAction.XFAIL:
                marks = pytest.mark.xfail(reason=reason, run=False)
            else:
                marks = None
        else:
            if load_attrs.marker_func is None:
                return default_markers
            else:
                if isinstance(loaded_data, LazyLoadedPartData):
                    # When `marks` callable is provided for the @parametrize loader, marks are generated when
                    # LazyLoadedPartData is created
                    marks = loaded_data.meta["marks"]
                else:
                    if load_attrs.loader.requires_parametrization:
                        assert loaded_data.gidx is not None
                        marks = load_attrs.marker_func(loaded_data.gidx, loaded_data.file_path, loaded_data.data)
                    else:
                        marks = load_attrs.marker_func(loaded_data.file_path, loaded_data.data)
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


def _emit_warning(msg: str, metafunc: Metafunc, loader_idx: int, load_attrs: DataLoaderLoadAttrs) -> None:
    decorator_src = (
        get_data_loader_source(metafunc.function, loader_idx, load_attrs.loader.__name__)
        or f"@{load_attrs.loader.__name__}"
    )
    warnings.warn(f"{msg}\n  - nodeid: {metafunc.definition.nodeid}\n  - data loader: {decorator_src}", UserWarning)
