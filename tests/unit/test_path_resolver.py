from pathlib import Path

import pytest
from pytest import FixtureRequest

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.loaders.impl import resolve_relative_path
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_JSON_FILE_OBJECT,
    PATH_SOME_DIR,
    PATH_TEXT_FILE,
)

pytestmark = pytest.mark.unittest


LOCAL_LOADER_DIR = Path(__file__).resolve().parent / DEFAULT_LOADER_DIR_NAME


def test_path_resolver_should_find_from_upper_dir(request: FixtureRequest) -> None:
    """Test that the relative path specified is located from an upper-level loader directory if one doesn't exist in
    the lower-level data directory
    """
    assert (ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).exists()
    assert not (LOCAL_LOADER_DIR / PATH_JSON_FILE_OBJECT).exists()
    data_loader_dir, resolved_path = resolve_relative_path(
        DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(PATH_JSON_FILE_OBJECT), Path(__file__), is_file=True
    )
    assert data_loader_dir == resolved_path.parent.parent.parent == ABS_PATH_LOADER_DIR


def test_path_resolver_should_find_nearest_file(request: FixtureRequest) -> None:
    """Test that the relative path specified is located from the nearest loader directory if the same path exists
    under multiple loader directories in the directory tree
    """
    assert (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).exists()
    assert (LOCAL_LOADER_DIR / PATH_TEXT_FILE).exists()
    data_loader_dir, resolved_path = resolve_relative_path(
        DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(PATH_TEXT_FILE), Path(__file__), is_file=True
    )
    assert data_loader_dir == resolved_path.parent.parent == LOCAL_LOADER_DIR


@pytest.mark.parametrize("is_file", [True, False])
def test_path_resolver_should_ignore_unmatched_path_type(request: FixtureRequest, is_file: bool) -> None:
    """Test that relative path for an unmatched path type should be ignored when the relative path is identical"""
    assert (ABS_PATH_LOADER_DIR / PATH_SOME_DIR).exists()
    assert (ABS_PATH_LOADER_DIR / PATH_SOME_DIR).is_dir()
    assert (LOCAL_LOADER_DIR / PATH_SOME_DIR).exists()
    assert (LOCAL_LOADER_DIR / PATH_SOME_DIR).is_file()

    data_loader_dir, resolved_path = resolve_relative_path(
        DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(PATH_SOME_DIR), Path(__file__), is_file=is_file
    )
    if is_file:
        assert data_loader_dir == resolved_path.parent == LOCAL_LOADER_DIR
    else:
        assert data_loader_dir == resolved_path.parent == ABS_PATH_LOADER_DIR


@pytest.mark.parametrize("is_file", [True, False])
@pytest.mark.parametrize("valid_loader_dir", [True, False])
def test_path_resolver_should_raise_error_if_not_found(
    request: FixtureRequest, valid_loader_dir: bool, is_file: bool
) -> None:
    """Test that non-existing path should be handled as FileNotFoundError error"""
    non_existing_path = Path("foo")
    if is_file:
        non_existing_path /= "bar.txt"

    data_loader_dir = DEFAULT_LOADER_DIR_NAME if valid_loader_dir else "invalid_dir"
    with pytest.raises(FileNotFoundError):
        resolve_relative_path(
            data_loader_dir, request.config.rootpath, non_existing_path, Path(__file__), is_file=is_file
        )
