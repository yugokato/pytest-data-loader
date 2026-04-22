import gc
from pathlib import Path

import pytest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.loaders.impl import DirectoryLoader, FileLoader
from pytest_data_loader.types import DataLoaderLoadAttrs, LazyLoadedData, LoadedData
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR, PATH_EMPTY_DIR, PATH_SOME_DIR, PATH_SOME_DIR_INNER

pytestmark = pytest.mark.unittest

# Number of non-hidden files in PATH_SOME_DIR (non-recursive)
_NUM_FILES_IN_SOME_DIR = 3


class TestDirectoryLoader:
    """Tests for directory loader with various configurations."""

    @pytest.mark.parametrize("is_abs_path", [False, True])
    @pytest.mark.parametrize("recursive", [False, True])
    @pytest.mark.parametrize("path", [PATH_SOME_DIR, PATH_EMPTY_DIR])
    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_directory_loader(self, lazy_loading: bool, path: str, is_abs_path: bool, recursive: bool) -> None:
        """Test directory loader with various file types and with/without lazy loading"""
        abs_dir_path = ABS_PATH_LOADER_DIR / path
        is_empty_dir = path == PATH_EMPTY_DIR
        if is_abs_path:
            path = abs_dir_path
            load_from = None
        else:
            load_from = ABS_PATH_LOADER_DIR
        load_attrs = DataLoaderLoadAttrs(
            loader=parametrize_dir,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=Path(path),
            lazy_loading=lazy_loading,
            recursive=recursive,
        )

        loaded_files = DirectoryLoader(
            abs_dir_path, load_attrs, load_from=load_from, strip_trailing_whitespace=True
        ).load()
        assert isinstance(loaded_files, list)

        if is_empty_dir:
            assert loaded_files == []
        else:
            assert len(loaded_files) > 0
            if recursive:
                assert any(f.file_path.is_relative_to(abs_dir_path / PATH_SOME_DIR_INNER) for f in loaded_files)
            else:
                assert not any(f.file_path.is_relative_to(abs_dir_path / PATH_SOME_DIR_INNER) for f in loaded_files)
            for loaded_data in loaded_files:
                file_path = loaded_data.file_path
                assert file_path.is_relative_to(abs_dir_path)
                assert not file_path.name.startswith(".")
                if lazy_loading:
                    assert isinstance(loaded_data, LazyLoadedData)
                    if is_abs_path:
                        assert loaded_data.file_path_relative is None
                        assert repr(loaded_data) == str(file_path)
                    else:
                        assert loaded_data.file_path_relative == file_path.relative_to(ABS_PATH_LOADER_DIR)
                        assert repr(loaded_data) == str(loaded_data.file_path_relative)
                else:
                    assert isinstance(loaded_data, LoadedData)


class TestDirectoryLoaderCaching:
    """Tests for DirectoryLoader cache state management"""

    def _make_load_attrs(self, lazy_loading: bool = True) -> DataLoaderLoadAttrs:
        """Create DataLoaderLoadAttrs for PATH_SOME_DIR.

        :param lazy_loading: Whether to use lazy loading
        """
        return DataLoaderLoadAttrs(
            loader=parametrize_dir,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=Path(PATH_SOME_DIR),
            lazy_loading=lazy_loading,
        )

    def _make_dir_loader(self, lazy_loading: bool = True) -> DirectoryLoader:
        """Create a DirectoryLoader for PATH_SOME_DIR.

        :param lazy_loading: Whether to use lazy loading
        """
        abs_dir_path = ABS_PATH_LOADER_DIR / PATH_SOME_DIR
        return DirectoryLoader(
            abs_dir_path,
            self._make_load_attrs(lazy_loading=lazy_loading),
            load_from=ABS_PATH_LOADER_DIR,
            strip_trailing_whitespace=True,
        )

    def test_directory_loader_file_loaders_populated(self) -> None:
        """Test that _file_loaders is populated with one FileLoader per file after load()"""
        dir_loader = self._make_dir_loader()

        loaded_files = dir_loader.load()

        assert isinstance(loaded_files, list)
        assert len(loaded_files) == _NUM_FILES_IN_SOME_DIR
        assert len(dir_loader._file_loaders) == _NUM_FILES_IN_SOME_DIR
        assert all(isinstance(c, FileLoader) for c in dir_loader._file_loaders)

    def test_directory_loader_clear_cache_delegates_to_children(self) -> None:
        """Test that clear_cache() calls clear_cache() on each child FileLoader and empties _file_loaders"""
        dir_loader = self._make_dir_loader(lazy_loading=True)
        loaded_files = dir_loader.load()

        # Each child has an lru_cache wrapper registered in _cached_file_loaders at load time
        assert len(dir_loader._file_loaders) == _NUM_FILES_IN_SOME_DIR
        for child in dir_loader._file_loaders:
            assert len(child._cached_file_loaders) == 1

        # Resolve all lazy data to exercise the lru_cache wrappers
        for lazy_data in loaded_files:
            assert isinstance(lazy_data, LazyLoadedData)
            lazy_data.resolve()

        # Capture child loader references before clearing (clear_cache empties the list)
        child_loaders = list(dir_loader._file_loaders)

        dir_loader.clear_cache()

        # _file_loaders is cleared
        assert dir_loader._file_loaders == []

        # All children's caches are also cleared
        for child in child_loaders:
            assert child._cached_file_loaders == set()
            assert child._cached_file_objects == {}
            assert child._cached_reader_split == {}

    def test_directory_loader_weakref_finalize(self) -> None:
        """Test that GC-ing a DirectoryLoader triggers the weakref finalizer, clearing child caches"""
        dir_loader = self._make_dir_loader(lazy_loading=True)
        loaded_files = dir_loader.load()

        assert len(dir_loader._file_loaders) == _NUM_FILES_IN_SOME_DIR

        # Capture references before deletion
        file_loaders_ref = dir_loader._file_loaders
        child_loaders = list(dir_loader._file_loaders)

        # Remove all strong references to dir_loader
        del loaded_files
        del dir_loader
        gc.collect()

        # Finalizer should have cleared _file_loaders (same list object)
        assert file_loaders_ref == []

        # Finalizer should have called clear_cache() on each child
        for child in child_loaders:
            assert child._cached_file_loaders == set()
            assert child._cached_file_objects == {}
            assert child._cached_reader_split == {}
