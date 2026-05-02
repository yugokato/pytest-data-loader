from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from _pytest.fixtures import FixtureRequest
from pytest import Config

from pytest_data_loader.constants import PYTEST_DATA_LOADER_MODULE_CACHE, STASH_KEY_DATA_LOADER_OPTION
from pytest_data_loader.loaders.impl import create_loaders
from pytest_data_loader.loaders.loaders import load
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderFunctionType,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    HashableDict,
    LoadedData,
    ReadOptions,
)
from pytest_data_loader.validators import validate_loader_func, validate_path, validate_read_options, validate_reader

if TYPE_CHECKING:
    from pytest_data_loader.loaders.impl import Loader


__all__ = ["DataLoaderFixture", "data_loader"]

logger = logging.getLogger(__name__)


@pytest.fixture
def data_loader(request: FixtureRequest, pytestconfig: Config) -> DataLoaderFixture:
    """Returns a callable that loads a single file and returns the file data.

    This is an alternative to the @load data loader for cases where the file path is only known at test time.
    """
    data_loader_option = pytestconfig.stash[STASH_KEY_DATA_LOADER_OPTION]
    return DataLoaderFixture(request, data_loader_option)


class DataLoaderFixture:
    """Callable returned by the data_loader fixture.

    Call it with a file path (absolute, or relative to the nearest data directory) to load a single
    file at test runtime.  Accepts the same reader, onload, and open() read options as @load.
    Repeated calls with the same arguments within a single test return the cached result without re-reading the file.
    """

    def __init__(self, request: FixtureRequest, data_loader_option: DataLoaderOption) -> None:
        """Initialize the data loader fixture.

        :param request: The active fixture request, used to locate the test file and module cache.
        :param data_loader_option: Parsed data loader INI options.
        """
        self._request = request
        self._data_loader_option = data_loader_option
        self._search_from = request.path
        self._cache: dict[tuple[Any, ...], Any] = {}

    def __call__(
        self,
        path: Path | str,
        /,
        *,
        reader: Callable[..., Iterable[Any] | object] | None = None,
        read_options: ReadOptions | None = None,
        onload: Callable[..., Any] | None = None,
    ) -> Any:
        """Load a single file and return its parsed data.

        :param path: Absolute path or a path relative to a data directory
        :param reader: A file reader the plugin should use to read the file data
        :param read_options: File read options the plugin passes to open() when reading the file
        :param onload: A function to transform or preprocess loaded data before passing it to the test function
        """
        loader = cast(DataLoader, load)
        validated_path = cast(Path, validate_path(path, loader=loader, recursive=False))
        validate_reader(reader)
        validate_read_options(read_options)
        validate_loader_func(onload, loader=loader, func_type=DataLoaderFunctionType.ONLOAD_FUNC)

        hashable_read_options = HashableDict(read_options or {})
        cache_key = (str(validated_path), reader, onload, tuple(sorted(hashable_read_options.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        load_attrs = DataLoaderLoadAttrs(
            loader=loader,
            search_from=self._search_from,
            fixture_names=("_",),
            path=validated_path,
            lazy_loading=False,
            reader=reader,
            read_options=hashable_read_options,
            onload_func=onload,
        )

        (file_loader,) = create_loaders(validated_path, load_attrs, self._data_loader_option)
        file_loader.register_cleanup(self._request.module)
        loaded = file_loader.load()
        assert isinstance(loaded, LoadedData)
        data = loaded.data
        self._cache[cache_key] = data
        return data


@pytest.fixture(scope="module", autouse=True)
def _pytest_data_loader_cleanup(request: FixtureRequest) -> Generator[None]:
    """Clear cache used by data loaders at the end of each module"""
    yield
    cached_data_loaders: set[Loader] | None
    if cached_data_loaders := getattr(request.module, PYTEST_DATA_LOADER_MODULE_CACHE, None):
        for cached_data_loader in cached_data_loaders:
            try:
                cached_data_loader.clear_cache()
            except Exception as e:
                logger.exception(e)
        cached_data_loaders.clear()
