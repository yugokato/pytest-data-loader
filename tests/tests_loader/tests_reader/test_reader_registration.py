from io import TextIOWrapper
from pathlib import Path

import pytest

from pytest_data_loader.loaders.reader import _DEFAULT_READERS, FileReader

pytestmark = pytest.mark.readers


@pytest.mark.parametrize("ext", _DEFAULT_READERS.keys())
def test_default_reader_registration(ext: str) -> None:
    """Test that default readers are implicitly registered"""
    assert ext not in FileReader._REGISTERED_READERS.keys()
    file_reader = FileReader.get_registered_reader(Path(__file__), ext)
    assert file_reader is not None
    assert file_reader is _DEFAULT_READERS[ext]


@pytest.mark.parametrize("with_read_options", [False, True])
def test_reader_registration(with_read_options: bool) -> None:
    """Test that a file reader can be registered by conftest paths with/without read options"""
    ext = ".dummy"
    fake_conftest_path = Path(".").resolve()
    assert FileReader.get_registered_reader(fake_conftest_path, ext) is None

    read_options = {}
    if with_read_options:
        read_options = {"mode": "rb"}
        file_reader = FileReader.register(fake_conftest_path, ext, TextIOWrapper, **read_options)
    else:
        file_reader = FileReader.register(fake_conftest_path, ext, TextIOWrapper)
    assert file_reader is not None
    assert file_reader.reader == TextIOWrapper
    assert dict(file_reader.read_options) == read_options
    assert fake_conftest_path in FileReader._REGISTERED_READERS

    assert FileReader._REGISTERED_READERS[fake_conftest_path][ext] is file_reader
    assert FileReader.get_registered_reader(fake_conftest_path, ext) is file_reader

    FileReader._unregister(fake_conftest_path, ext)
    assert FileReader.get_registered_reader(fake_conftest_path, ext) is None
