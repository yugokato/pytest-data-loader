from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from _pytest.fixtures import FixtureRequest
from pytest import Config

from pytest_data_loader.compat import Unpack
from pytest_data_loader.constants import PYTEST_DATA_LOADER_MODULE_CACHE, STASH_KEY_DATA_LOADER_OPTION
from pytest_data_loader.loaders.impl import create_loaders
from pytest_data_loader.loaders.loaders import load
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    FileReadOptions,
    HashableDict,
    LoadedData,
)

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
    file at test runtime.  Accepts the same file_reader, onload_func, and open() read options as @load.
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
        file_reader: Callable[..., Iterable[Any] | object] | None = None,
        onload_func: Callable[..., Any] | None = None,
        **read_options: Unpack[FileReadOptions],
    ) -> Any:
        """Load a single file and return its parsed data.

        :param path: Absolute path or a path relative to a data directory
        :param file_reader: A file reader the plugin should use to read the file data
        :param onload_func: A function to transform or preprocess loaded data before passing it to the test function
        :param read_options: File read options the plugin passes to open() when reading the file
        """
        cache_key = (str(path), file_reader, onload_func, tuple(sorted(read_options.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = Path(path)
        load_attrs = DataLoaderLoadAttrs(
            loader=cast(DataLoader, load),
            search_from=self._search_from,
            fixture_names=("_",),
            path=path,
            lazy_loading=False,
            file_reader=file_reader,
            onload_func=onload_func,
            read_options=HashableDict(read_options),
        )

        (file_loader,) = create_loaders(path, load_attrs, self._data_loader_option)
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
