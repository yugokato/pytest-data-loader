from pathlib import Path

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.impl import FileDataLoader
from pytest_data_loader.types import DataLoader, DataLoaderLoadAttrs, LazyLoadedData, LazyLoadedPartData, LoadedData
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_JPEG_FILE,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_OBJECT,
    PATH_JSON_FILE_SCALAR,
    PATH_TEXT_FILE,
)


@pytest.mark.parametrize(
    "relative_path",
    [PATH_TEXT_FILE, PATH_JSON_FILE_OBJECT, PATH_JSON_FILE_ARRAY, PATH_JSON_FILE_SCALAR, PATH_JPEG_FILE],
)
@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader(loader: DataLoader, lazy_loading: bool, relative_path: str) -> None:
    """Test file loader with various file types and with/without lazy loading"""
    abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
    filename = abs_file_path.name
    marks = (pytest.mark.foo, pytest.mark.bar)
    load_attrs = DataLoaderLoadAttrs(
        loader=loader,
        fixture_names=("file_path", "data"),
        relative_path=Path(relative_path),
        lazy_loading=lazy_loading,
        # for @parametrize loader with lazy loading
        id_func=lambda x: x,
        marker_func=lambda x: marks,
    )

    loaded_data = FileDataLoader(abs_file_path, load_attrs=load_attrs, strip_trailing_whitespace=True).load()

    if lazy_loading:
        if loader == parametrize:
            assert isinstance(loaded_data, tuple)
            for lazy_loaded_part in loaded_data:
                assert isinstance(lazy_loaded_part, LazyLoadedPartData)
                assert lazy_loaded_part.file_path == abs_file_path
                assert lazy_loaded_part.idx >= 0
                assert lazy_loaded_part.offset >= 0
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
            assert isinstance(loaded_data, tuple)
            for loaded_part in loaded_data:
                assert isinstance(loaded_part, LoadedData)
                assert loaded_part.file_path == abs_file_path
        else:
            assert isinstance(loaded_data, LoadedData)
            assert loaded_data.file_path == abs_file_path


@pytest.mark.parametrize("relative_path", [PATH_TEXT_FILE, PATH_JSON_FILE_OBJECT])
@pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
def test_file_loader_cache(loader: DataLoader, relative_path: str) -> None:
    """Test the file loader's two different cache logic used for the @parametrize loader with lazy loading.
    Also make sure that other loaders do not use cache
    """
    abs_file_path = ABS_PATH_LOADER_DIR / relative_path
    load_attrs = DataLoaderLoadAttrs(
        loader=loader, fixture_names=("file_path", "data"), relative_path=Path(relative_path), lazy_loading=True
    )
    file_loader = FileDataLoader(abs_file_path, load_attrs=load_attrs, strip_trailing_whitespace=True)

    if relative_path == PATH_TEXT_FILE:
        assert file_loader.is_streamable
    elif relative_path == PATH_JSON_FILE_OBJECT:
        assert not file_loader.is_streamable
    else:
        raise NotImplementedError("Unsupported test")

    lazy_loaded_data = file_loader._load_lazily()

    assert file_loader._cached_file_objects == {}
    assert file_loader._cached_loader_functions == set()

    if loader == parametrize:
        assert isinstance(lazy_loaded_data, tuple)
        assert all(isinstance(x, LazyLoadedPartData) for x in lazy_loaded_data)
        for i, lazy_data in enumerate(lazy_loaded_data):
            lazy_data.resolve()
            if file_loader.is_streamable:
                # The file object should be cached
                assert len(file_loader._cached_file_objects) == 1
                assert abs_file_path in file_loader._cached_file_objects
            else:
                # The file loader function should be cached
                assert lazy_data.file_loader in file_loader._cached_loader_functions
                cache_info = lazy_data.file_loader.cache_info()
                if i == 0:
                    assert cache_info.hits == 0
                    assert cache_info.misses == 1
                else:
                    assert cache_info.hits == i
                    assert cache_info.misses == 1

        # Clear cache
        file_loader.clear_cache()
        assert file_loader._cached_file_objects == {}
        assert file_loader._cached_loader_functions == set()
    else:
        assert isinstance(lazy_loaded_data, LazyLoadedData)
        lazy_loaded_data.resolve()
        # cache will not be used
        assert file_loader._cached_file_objects == {}
        assert file_loader._cached_loader_functions == set()
