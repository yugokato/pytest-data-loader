from collections.abc import Callable
from functools import _CacheInfo
from pathlib import Path
from typing import Any

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.impl import FileDataLoader
from pytest_data_loader.types import DataLoader, DataLoaderLoadAttrs, LazyLoadedData, LazyLoadedPartData, LoadedData
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_CSV_FILE,
    PATH_INI_FILE,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_OBJECT,
    PATH_JSON_FILE_SCALAR,
    PATH_TEXT_FILE,
    PATH_TOML_FILE,
    PATH_XML_FILE,
    PATH_YAML_FILE,
)

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize(
    "relative_path",
    [
        # PATH_TEXT_FILE,
        PATH_JSON_FILE_OBJECT,
        # PATH_JSON_FILE_ARRAY,
        # PATH_JSON_FILE_SCALAR,
        # PATH_CSV_FILE,
        # PATH_XML_FILE,
        # PATH_YAML_FILE,
        # PATH_TOML_FILE,
        # PATH_INI_FILE,
        # PATH_JPEG_FILE,
    ],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader(loader: DataLoader, lazy_loading: bool, relative_path: Path) -> None:
    """Test file loader with various file types and with/without lazy loading"""
    abs_file_path = ABS_PATH_LOADER_DIR / relative_path
    filename = abs_file_path.name
    marks = (pytest.mark.foo, pytest.mark.bar)
    load_attrs = DataLoaderLoadAttrs(
        loader=loader,
        fixture_names=("file_path", "data"),
        relative_path=relative_path,
        lazy_loading=lazy_loading,
        # for @parametrize loader with lazy loading
        id_func=lambda x: repr(x),
        marker_func=lambda x: marks,
    )

    file_loader = FileDataLoader(abs_file_path, load_attrs=load_attrs, strip_trailing_whitespace=True)
    if relative_path.suffix == ".json":
        assert file_loader.file_reader is not None
    loaded_data = file_loader.load()

    if lazy_loading:
        if loader == parametrize:
            assert isinstance(loaded_data, list)
            for lazy_loaded_part in loaded_data:
                assert isinstance(lazy_loaded_part, LazyLoadedPartData)
                assert lazy_loaded_part.file_path == abs_file_path
                assert lazy_loaded_part.idx >= 0
                assert lazy_loaded_part.pos >= 0
                assert repr(lazy_loaded_part) == f"{filename}:part{lazy_loaded_part.idx + 1}"
                assert set(lazy_loaded_part.meta.keys()) == {"marks", "id"}
                assert lazy_loaded_part.meta["id"] > ""
                assert lazy_loaded_part.meta["marks"] == marks
        else:
            assert isinstance(loaded_data, LazyLoadedData)
            assert loaded_data.file_path == abs_file_path
            assert repr(loaded_data) == f"{filename}"
    else:
        if loader == parametrize:
            assert isinstance(loaded_data, list)
            for loaded_part in loaded_data:
                assert isinstance(loaded_part, LoadedData)
                assert loaded_part.file_path == abs_file_path
        else:
            assert isinstance(loaded_data, LoadedData)
            assert loaded_data.file_path == abs_file_path


@pytest.mark.parametrize(
    "relative_path",
    [
        PATH_TEXT_FILE,
        PATH_JSON_FILE_OBJECT,
        PATH_JSON_FILE_ARRAY,
        PATH_JSON_FILE_SCALAR,
        PATH_CSV_FILE,
        PATH_XML_FILE,
        PATH_YAML_FILE,
        PATH_TOML_FILE,
        PATH_INI_FILE,
    ],
)
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader_cached_file_loaders(loader: DataLoader, relative_path: Path) -> None:
    """Test the file loader's three different cache logic used for the @parametrize loader with lazy loading.
    Also make sure that other loaders do not use cache
    """
    abs_file_path = ABS_PATH_LOADER_DIR / relative_path
    load_attrs = DataLoaderLoadAttrs(
        loader=loader, fixture_names=("file_path", "data"), relative_path=relative_path, lazy_loading=True
    )
    file_loader = FileDataLoader(abs_file_path, load_attrs=load_attrs, strip_trailing_whitespace=True)
    if relative_path.suffix == ".json":
        assert file_loader.file_reader is not None

    if relative_path in (
        PATH_TEXT_FILE,
        PATH_JSON_FILE_OBJECT,
        PATH_JSON_FILE_ARRAY,
        PATH_JSON_FILE_SCALAR,
        PATH_CSV_FILE,
    ):
        assert file_loader.is_streamable
    else:
        assert not file_loader.is_streamable

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
