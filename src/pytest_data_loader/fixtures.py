from __future__ import annotations

import logging
import warnings
from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from _pytest.fixtures import FixtureRequest

from pytest_data_loader.constants import PYTEST_DATA_LOADER_MODULE_CACHE, STASH_KEY_DATA_LOADER_OPTION
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.loaders.impl import create_loaders
from pytest_data_loader.loaders.loaders import load
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderFunctionType,
    DataLoaderLoadAttrs,
    DataLoaderOnMissingAction,
    DataLoaderOption,
    FileReader,
    FixtureScope,
    HashableDict,
    LoadedData,
    OnloadFunc,
    ReadOptions,
)
from pytest_data_loader.utils import get_caller_path
from pytest_data_loader.validators import (
    validate_fixture_scope,
    validate_loader_func,
    validate_path,
    validate_read_options,
    validate_reader,
)

if TYPE_CHECKING:
    from pytest_data_loader.loaders.impl import Loader


__all__ = ["DataLoaderFixture", "data_loader", "make_data_loader_fixture"]

logger = logging.getLogger(__name__)


def make_data_loader_fixture(scope: FixtureScope) -> Callable[..., Any]:
    """Create a data loader fixture with the specified scope.

    Assign the returned fixture to a module-level name in a `conftest.py` or a test module (not in a class body).
    The name becomes the fixture name. The fixture provides a callable that loads a single file at runtime, the same
    way as the built-in `data_loader` fixture. Loaded data is cached until the fixture is torn down.

    A relative path is searched from the test file for the function, class, and module scopes. The package and session
    scopes have no single test file, so the file that calls this function is used instead.

    :param scope: The fixture scope. Use a scope that is equal to or wider than the scope of the fixtures and tests
                  that need the data
    """
    validate_fixture_scope(scope)
    defined_in = None if scope in ("function", "class", "module") else get_caller_path()

    @pytest.fixture(scope=scope)
    def _data_loader(request: FixtureRequest) -> Generator[DataLoaderFixture]:
        """Returns a callable that loads a single file and returns the file data.

        This is an alternative to the @load data loader for cases where the file path is only known at runtime.
        The loaded data is cached until the fixture is torn down.
        """
        data_loader_option = request.config.stash[STASH_KEY_DATA_LOADER_OPTION]
        loader = DataLoaderFixture(data_loader_option, search_from=defined_in or request.path)
        yield loader
        loader.clear_cache()

    return _data_loader


data_loader = make_data_loader_fixture(scope="function")


class DataLoaderFixture:
    """Callable returned by a data loader fixture.

    Call it with a file path (absolute, or relative to the nearest data directory) to load a single
    file at runtime.  Accepts the same reader, onload, and open() read options as @load.
    Loaded data is cached for the lifetime of the fixture, so repeated calls with the same arguments return the same
    data without re-reading the file.
    One-shot iterators (e.g. generators from a .jsonl reader) are intentionally not cached so each call
    returns a fresh iterator.
    """

    def __init__(self, data_loader_option: DataLoaderOption, *, search_from: Path) -> None:
        """Initialize the data loader fixture.

        :param data_loader_option: Parsed data loader INI options.
        :param search_from: The location to start searching for the data directory and registered file readers from.
        """
        self._data_loader_option = data_loader_option
        self._search_from = search_from
        self._cache: dict[tuple[Any, ...], Any] = {}
        self._file_loaders: list[Loader] = []

    def __call__(
        self,
        path: Path | str,
        /,
        *,
        reader: FileReader | None = None,
        read_options: ReadOptions | None = None,
        onload: OnloadFunc | None = None,
    ) -> Any:
        """Load a single file and return its parsed data.

        :param path: Absolute path or a path relative to a data directory.
                     Environment variables are supported using the ``${VAR}`` or ``$VAR``
                     (or ``%VAR%`` for Windows) syntax.
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

        try:
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
            self._file_loaders.append(file_loader)
            loaded = file_loader.load()
            assert isinstance(loaded, LoadedData)
            data = loaded.data
            if not isinstance(data, Iterator):
                # Skip caching one-shot iterators: the same exhausted object would be returned on the next call.
                self._cache[cache_key] = data
            return data
        except DataNotFound as e:
            return self._handle_missing_data(cache_key, e)

    def clear_cache(self) -> None:
        """Clear the cached data and release the file handles held by the loaders this fixture created."""
        for file_loader in self._file_loaders:
            file_loader.clear_cache()
        self._file_loaders.clear()
        self._cache.clear()

    def _handle_missing_data(self, cache_key: tuple[Any, ...], exc: DataNotFound) -> Any:
        """Dispatch a missing-path DataNotFound at test runtime based on the on_missing option.

        :param cache_key: Cache key used to deduplicate repeated calls for the same missing path
        :param exc: The DataNotFound exception describing the missing path
        """
        on_missing = self._data_loader_option.on_missing
        reason = f"{type(exc).__name__}: {exc}"
        if on_missing == DataLoaderOnMissingAction.RAISE:
            raise exc
        elif on_missing == DataLoaderOnMissingAction.SKIP:
            pytest.skip(reason=reason)
        elif on_missing == DataLoaderOnMissingAction.XFAIL:
            pytest.xfail(reason=reason)
        elif on_missing == DataLoaderOnMissingAction.WARN:
            warnings.warn(reason, UserWarning, stacklevel=3)
            self._cache[cache_key] = None
        return None


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
