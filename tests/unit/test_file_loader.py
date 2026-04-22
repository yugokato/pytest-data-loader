import gc
from collections.abc import Callable
from functools import _CacheInfo
from pathlib import Path
from typing import Any

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.impl import FileLoader
from pytest_data_loader.types import DataLoader, DataLoaderLoadAttrs, LazyLoadedData, LazyLoadedPartData, LoadedData
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_JSON_FILE_ARRAY,
    PATH_JSONL_FILE,
    PATH_TEXT_FILE,
    PATH_XML_FILE,
    PATHS_BINARY_FILES,
    PATHS_TEXT_FILES,
)

pytestmark = pytest.mark.unittest


class TestFileLoader:
    """Tests for file loader with various file types and loading modes."""

    @pytest.mark.parametrize("is_abs_path", [False, True])
    @pytest.mark.parametrize("path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES])
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
    def test_file_loader(self, loader: DataLoader, lazy_loading: bool, path: Path, is_abs_path: bool) -> None:
        """Test file loader with various file types and with/without lazy loading"""
        abs_file_path = ABS_PATH_LOADER_DIR / path
        if is_abs_path:
            path = abs_file_path
            load_from = None
        else:
            load_from = ABS_PATH_LOADER_DIR
        if loader == parametrize_dir:
            path = path.parent
        is_binary = abs_file_path.relative_to(ABS_PATH_LOADER_DIR) in PATHS_BINARY_FILES
        marks = (pytest.mark.foo, pytest.mark.bar)
        load_attrs = DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=path,
            lazy_loading=lazy_loading,
            parametrizer_func=(lambda x: [x]) if is_binary else None,
            # for @parametrize loader with lazy loading
            id_func=repr,
            marker_func=lambda _: marks,
        )

        file_loader = FileLoader(abs_file_path, load_attrs, load_from=load_from, strip_trailing_whitespace=True)
        if path.suffix == ".json":
            assert file_loader.file_reader is not None
        loaded_data = file_loader.load()

        if lazy_loading:
            if loader == parametrize:
                assert isinstance(loaded_data, list)
                for lazy_loaded_part in loaded_data:
                    assert isinstance(lazy_loaded_part, LazyLoadedPartData)
                    assert lazy_loaded_part.file_path == abs_file_path
                    assert lazy_loaded_part.idx >= 0
                    if file_loader.is_streamable:
                        assert lazy_loaded_part.pos is not None
                        assert lazy_loaded_part.pos >= 0
                    else:
                        assert lazy_loaded_part.pos is None
                    if is_abs_path:
                        assert lazy_loaded_part.file_path_relative is None
                        assert repr(lazy_loaded_part) == f"{abs_file_path}:part{lazy_loaded_part.idx + 1}"
                    else:
                        assert lazy_loaded_part.file_path_relative == abs_file_path.relative_to(ABS_PATH_LOADER_DIR)
                        assert (
                            repr(lazy_loaded_part)
                            == f"{lazy_loaded_part.file_path_relative}:part{lazy_loaded_part.idx + 1}"
                        )
                    assert set(lazy_loaded_part.meta.keys()) == {"marks", "id"}
                    assert lazy_loaded_part.meta["id"] > ""
                    assert lazy_loaded_part.meta["marks"] == marks
            else:
                assert isinstance(loaded_data, LazyLoadedData)
                assert loaded_data.file_path == abs_file_path
                if is_abs_path:
                    assert loaded_data.file_path_relative is None
                    assert repr(loaded_data) == str(abs_file_path)
                else:
                    assert loaded_data.file_path_relative == loaded_data.file_path.relative_to(ABS_PATH_LOADER_DIR)
                    assert repr(loaded_data) == str(loaded_data.file_path_relative)
        else:
            if loader == parametrize:
                assert isinstance(loaded_data, list)
                for loaded_part in loaded_data:
                    assert isinstance(loaded_part, LoadedData)
                    assert loaded_part.file_path == abs_file_path
            else:
                assert isinstance(loaded_data, LoadedData)
                assert loaded_data.file_path == abs_file_path

    @pytest.mark.parametrize("data", ["test", b"\x00\x01\x02"])
    def test_read_mode_detection(self, tmp_path: Path, data: str | bytes) -> None:
        """Test that file loading can detect the file read mode"""
        abs_file_path = tmp_path / "file.bin"
        if isinstance(data, bytes):
            abs_file_path.write_bytes(data)
            expected_mode = "rb"
        else:
            abs_file_path.write_text(data)
            expected_mode = "r"

        load_attrs = DataLoaderLoadAttrs(
            loader=load, search_from=Path(__file__), fixture_names=("data",), path=abs_file_path, lazy_loading=False
        )
        file_loader = FileLoader(abs_file_path, load_attrs)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == data
        assert file_loader.read_mode == expected_mode


class TestFileLoaderCaching:
    """Tests for FileLoader cache state management across loading modes"""

    @staticmethod
    def check_lru_cache_result(
        f: Callable[..., Any], expected_hits: int, expected_misses: int, expected_maxsize: int, expected_currsize: int
    ) -> None:
        """Check lru_cache result. Only the first item should miss the cache.

        :param f: The lru_cache-wrapped callable to inspect
        :param expected_hits: Expected number of cache hits
        :param expected_misses: Expected number of cache misses
        :param expected_maxsize: Expected maxsize of the cache
        :param expected_currsize: Expected current number of cached entries
        """
        cache_info: _CacheInfo = f.cache_info()  # type: ignore[attr-defined]
        assert cache_info.hits == expected_hits
        assert cache_info.misses == expected_misses
        assert cache_info.maxsize == expected_maxsize
        assert cache_info.currsize == expected_currsize

    def _make_load_attrs(
        self,
        loader: DataLoader,
        path: Path,
        lazy_loading: bool = True,
        parametrizer_func: Callable[..., Any] | None = None,
    ) -> DataLoaderLoadAttrs:
        """Create a minimal DataLoaderLoadAttrs for testing.

        :param loader: The data loader to use
        :param path: Relative path to the test data file
        :param lazy_loading: Whether to use lazy loading
        :param parametrizer_func: Optional parametrizer function (e.g. for binary files)
        """
        return DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=path,
            lazy_loading=lazy_loading,
            parametrizer_func=parametrizer_func,
        )

    @pytest.mark.parametrize("path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES])
    @pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
    def test_lazy_loading_cache_state_transitions(self, loader: DataLoader, path: Path) -> None:
        """Test that lazy loading correctly transitions cache state before and after resolve and clear_cache."""
        abs_file_path = ABS_PATH_LOADER_DIR / path
        parametrizer_func: Callable[..., Any] | None = (lambda x: [x]) if path in PATHS_BINARY_FILES else None
        load_attrs = self._make_load_attrs(loader, path, lazy_loading=True, parametrizer_func=parametrizer_func)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        if path.suffix == ".json":
            assert file_loader.file_reader is not None

        lazy_loaded_data = file_loader._load_lazily()

        assert file_loader._cached_file_objects == {}
        # For streamable @parametrize files, no lru_cache wrapper is created at load time.
        # For all other cases, the file_loader is registered eagerly to ensure cleanup even if tests are skipped.
        if loader == parametrize and file_loader.is_streamable:
            assert file_loader._cached_file_loaders == set()
        else:
            assert len(file_loader._cached_file_loaders) == 1
        assert file_loader._cached_reader_split == {}

        if loader == parametrize:
            assert isinstance(lazy_loaded_data, list)
            assert all(isinstance(x, LazyLoadedPartData) for x in lazy_loaded_data)
            for i, lazy_data in enumerate(lazy_loaded_data):
                lazy_data.resolve()
                if file_loader.is_streamable:
                    # The file object should be cached, but file loader should not be cached
                    assert not hasattr(lazy_data.file_loader_func, "cache_info")
                    assert len(file_loader._cached_file_objects) == 1
                    assert lazy_data.file_loader_func not in file_loader._cached_file_loaders
                    assert (abs_file_path, file_loader.read_options) in file_loader._cached_file_objects
                    if file_loader.file_reader:
                        # The result of _read_reader_and_split() should be cached per reader
                        assert file_loader.file_reader in file_loader._cached_reader_split
                else:
                    # The file object should not be cached, but the file loader function should be cached
                    assert hasattr(lazy_data.file_loader_func, "cache_info")
                    assert len(file_loader._cached_file_objects) == 0
                    assert lazy_data.file_loader_func in file_loader._cached_file_loaders
                    self.check_lru_cache_result(lazy_data.file_loader_func, i, 1, 1, 1)
        else:
            assert isinstance(lazy_loaded_data, LazyLoadedData)
            assert hasattr(lazy_loaded_data.file_loader_func, "cache_info")
            lazy_loaded_data.resolve()
            # The file loader function should be cached for reuse across stacked parametrize calls
            assert lazy_loaded_data.file_loader_func in file_loader._cached_file_loaders
            self.check_lru_cache_result(lazy_loaded_data.file_loader_func, 0, 1, 1, 1)

        # Clear cache
        file_loader.clear_cache()
        assert file_loader._cached_file_objects == {}
        assert file_loader._cached_file_loaders == set()
        assert file_loader._cached_reader_split == {}

    def test_eager_loading_has_no_data_cache(self) -> None:
        """Test that eager loading does not populate lru_cache or reader_split caches for a plain text file"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
        load_attrs = self._make_load_attrs(load, PATH_TEXT_FILE, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert file_loader.file_reader is None

        file_loader.load()

        assert file_loader._cached_file_loaders == set()
        assert file_loader._cached_reader_split == {}
        assert file_loader._cached_file_objects == {}

    def test_eager_loading_with_file_reader_caches_file_obj(self) -> None:
        """Test that eager loading with a file_reader caches the open file handle in _cached_file_objects"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_ARRAY, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert file_loader.file_reader is not None

        file_loader.load()

        assert file_loader._cached_file_loaders == set()
        assert file_loader._cached_reader_split == {}
        assert len(file_loader._cached_file_objects) == 1
        assert (abs_file_path, file_loader.read_options) in file_loader._cached_file_objects

        file_loader.clear_cache()
        assert file_loader._cached_file_objects == {}

    def test_non_streamable_parametrize_lazy_double_load(self) -> None:
        """Test that non-streamable @parametrize lazy loading intentionally calls _load_now twice:
        once at collection (to count parametrized items) and once at first test setup (lru_cache miss)
        """
        # XML has no registered file_reader and a non-streamable suffix, making it non-streamable
        # for @parametrize, unlike JSON which is streamable because it has a registered file_reader.
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_XML_FILE
        load_attrs = self._make_load_attrs(parametrize, PATH_XML_FILE, lazy_loading=True)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert not file_loader.is_streamable
        assert file_loader.file_reader is None

        # Wrap _load_now to count how many times it is actually invoked
        call_count = 0
        original_load_now = file_loader._load_now

        def counting_load_now() -> LoadedData | list[LoadedData]:
            """Counting wrapper around the original _load_now."""
            nonlocal call_count
            call_count += 1
            return original_load_now()

        file_loader._load_now = counting_load_now

        # Collection phase: _load_now is called once directly to determine item count
        lazy_parts = file_loader._load_lazily()
        assert isinstance(lazy_parts, list)
        assert len(lazy_parts) > 1
        assert call_count == 1, "Expected exactly one _load_now call during collection"
        assert len(file_loader._cached_file_loaders) == 1
        cached_loader = next(iter(file_loader._cached_file_loaders))
        # lru_cache wrapper has not been invoked yet (0 hits, 0 misses)
        self.check_lru_cache_result(cached_loader, 0, 0, 1, 0)

        # First resolve: lru_cache miss — counting_load_now is called a second time
        lazy_parts[0].resolve()
        assert call_count == 2, "Expected a second _load_now call on first resolve (lru_cache miss)"
        self.check_lru_cache_result(cached_loader, 0, 1, 1, 1)

        # Second resolve: lru_cache hit — counting_load_now is NOT called again
        lazy_parts[1].resolve()
        assert call_count == 2, "Expected no additional _load_now call on second resolve (lru_cache hit)"
        self.check_lru_cache_result(cached_loader, 1, 1, 1, 1)

        file_loader.clear_cache()

    def test_cached_reader_split_reuse_across_resolves(self) -> None:
        """Test that _cached_reader_split is populated on the first resolve and the same list object
        is reused on subsequent resolves without re-reading the file
        """
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSONL_FILE
        load_attrs = self._make_load_attrs(parametrize, PATH_JSONL_FILE, lazy_loading=True)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert file_loader.is_streamable
        assert file_loader.file_reader is not None

        lazy_parts = file_loader._load_lazily()
        assert isinstance(lazy_parts, list)
        assert len(lazy_parts) > 1

        # No cached split before any resolve
        assert file_loader._cached_reader_split == {}

        # First resolve: file is read and the result list is cached in _cached_reader_split
        lazy_parts[0].resolve()
        assert file_loader.file_reader in file_loader._cached_reader_split
        first_list_id = id(file_loader._cached_reader_split[file_loader.file_reader])

        # Second resolve: the same cached list object is reused (no re-read)
        lazy_parts[1].resolve()
        assert file_loader.file_reader in file_loader._cached_reader_split
        assert id(file_loader._cached_reader_split[file_loader.file_reader]) == first_list_id

        file_loader.clear_cache()

    def test_weakref_finalize_clears_cache_on_gc(self) -> None:
        """Test that GC-ing a FileLoader triggers the weakref finalizer, closing cached file handles"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_ARRAY, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        file_loader.load()

        # Eager loading with file_reader caches an open file handle
        assert len(file_loader._cached_file_objects) == 1
        f_handle = next(iter(file_loader._cached_file_objects.values()))
        assert not f_handle.closed

        # Capture references to the cache containers before deleting the loader
        cached_file_objects_ref = file_loader._cached_file_objects
        cached_file_loaders_ref = file_loader._cached_file_loaders
        cached_reader_split_ref = file_loader._cached_reader_split

        del file_loader
        gc.collect()

        # Finalizer should have closed the file handle and cleared all cache containers
        assert f_handle.closed
        assert cached_file_objects_ref == {}
        assert cached_file_loaders_ref == set()
        assert cached_reader_split_ref == {}
