from pathlib import Path

import pytest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.loaders.impl import DirectoryDataLoader
from pytest_data_loader.types import DataLoaderLoadAttrs, LazyLoadedData, LoadedData
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR, PATH_EMPTY_DIR, PATH_SOME_DIR, PATH_SOME_DIR_INNER

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("is_abs_path", [False, True])
@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("path", [PATH_SOME_DIR, PATH_EMPTY_DIR])
@pytest.mark.parametrize("lazy_loading", [True, False])
def test_directory_loader(lazy_loading: bool, path: str, is_abs_path: bool, recursive: bool) -> None:
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

    loaded_files = DirectoryDataLoader(
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
