from pathlib import Path

import pytest

from pytest_data_loader import parametrize_dir
from pytest_data_loader.loaders.impl import DirectoryDataLoader
from pytest_data_loader.types import DataLoaderLoadAttrs, LazyLoadedData, LoadedData
from tests.tests_loader.helper import ABS_PATH_LOADER_DIR, PATH_EMPTY_DIR, PATH_SOME_DIR

pytestmark = pytest.mark.unittest


@pytest.mark.parametrize("path", [PATH_SOME_DIR, PATH_EMPTY_DIR])
@pytest.mark.parametrize("lazy_loading", [True, False])
def test_directory_loader(lazy_loading: bool, path: str) -> None:
    """Test directory loader with various file types and with/without lazy loading"""
    abs_dir_path = ABS_PATH_LOADER_DIR / path
    load_attrs = DataLoaderLoadAttrs(
        loader=parametrize_dir,
        search_from=Path(__file__),
        fixture_names=("file_path", "data"),
        path=Path(path),
        lazy_loading=lazy_loading,
    )

    loaded_files = DirectoryDataLoader(abs_dir_path, load_attrs=load_attrs, strip_trailing_whitespace=True).load()
    assert isinstance(loaded_files, list)

    if path == PATH_EMPTY_DIR:
        assert loaded_files == []
    else:
        assert len(loaded_files) > 0
        for loaded_data in loaded_files:
            assert loaded_data.file_path.is_relative_to(abs_dir_path)
            if lazy_loading:
                assert isinstance(loaded_data, LazyLoadedData)
                assert repr(loaded_data) == loaded_data.file_name
            else:
                assert isinstance(loaded_data, LoadedData)
