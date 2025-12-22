from collections.abc import Callable
from functools import _CacheInfo
from pathlib import Path
from typing import Any

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.impl import FileDataLoader
from pytest_data_loader.types import DataLoader, DataLoaderLoadAttrs, LazyLoadedData, LazyLoadedPartData, LoadedData
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR, PATHS_BINARY_FILES, PATHS_TEXT_FILES

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("is_abs_path", [False, True])
@pytest.mark.parametrize("path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES])
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader(loader: DataLoader, lazy_loading: bool, path: Path, is_abs_path: bool) -> None:
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
        id_func=lambda x: repr(x),
        marker_func=lambda x: marks,
    )

    file_loader = FileDataLoader(abs_file_path, load_attrs, load_from=load_from, strip_trailing_whitespace=True)
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


@pytest.mark.parametrize("path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES])
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader_cached_file_loaders(loader: DataLoader, path: Path) -> None:
    """Test the file loader's three different cache logic used for the @parametrize loader with lazy loading.
    Also make sure that other loaders do not use cache
    """
    abs_file_path = ABS_PATH_LOADER_DIR / path
    load_attrs = DataLoaderLoadAttrs(
        loader=loader,
        search_from=Path(__file__),
        fixture_names=("file_path", "data"),
        path=path,
        lazy_loading=True,
        parametrizer_func=(lambda x: [x]) if path in PATHS_BINARY_FILES else None,
    )
    file_loader = FileDataLoader(
        abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
    )
    if path.suffix == ".json":
        assert file_loader.file_reader is not None

    lazy_loaded_data = file_loader._load_lazily()

    assert file_loader._cached_file_objects == {}
    assert file_loader._cached_file_loaders == set()
    check_lru_cache_result(file_loader._read_reader_and_split, 0, 0, 1, 0)

    if loader == parametrize:
        assert isinstance(lazy_loaded_data, list)
        assert all(isinstance(x, LazyLoadedPartData) for x in lazy_loaded_data)
        for i, lazy_data in enumerate(lazy_loaded_data):
            lazy_data.resolve()
            if file_loader.is_streamable:
                assert not hasattr(lazy_data.file_loader, "cache_info")
                # The file object should be cached
                assert len(file_loader._cached_file_objects) == 1
                assert (abs_file_path, file_loader.read_options) in file_loader._cached_file_objects
                if file_loader.file_reader:
                    # The result of _read_reader_and_split() should be cached
                    check_lru_cache_result(file_loader._read_reader_and_split, i, 1, 1, 1)
            else:
                # The file loader function should be cached
                assert hasattr(lazy_data.file_loader, "cache_info")
                assert lazy_data.file_loader in file_loader._cached_file_loaders
                check_lru_cache_result(lazy_data.file_loader, i, 1, 1, 1)

        # Clear cache
        file_loader.clear_cache()
        assert file_loader._cached_file_objects == {}
        assert file_loader._cached_file_loaders == set()
        check_lru_cache_result(file_loader._read_reader_and_split, 0, 0, 1, 0)
    else:
        assert isinstance(lazy_loaded_data, LazyLoadedData)
        lazy_loaded_data.resolve()
        # cache will not be used
        assert file_loader._cached_file_objects == {}
        assert file_loader._cached_file_loaders == set()
        check_lru_cache_result(file_loader._read_reader_and_split, 0, 0, 1, 0)


def check_lru_cache_result(
    f: Callable[..., Any], expected_hits: int, expected_misses: int, expected_maxsize: int, expected_currsize: int
) -> None:
    """Check lru_cache result. Only the first item should miss the cache"""
    cache_info: _CacheInfo = f.cache_info()  # type: ignore[attr-defined]
    assert cache_info.hits == expected_hits
    assert cache_info.misses == expected_misses
    assert cache_info.maxsize == expected_maxsize
    assert cache_info.currsize == expected_currsize
