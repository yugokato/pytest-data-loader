import inspect
import keyword
import os
from collections.abc import Callable, Generator, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from pytest import Config

from pytest_data_loader.types import (
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
    UnsupportedFuncArg,
)


def parse_ini_option(config: Config, option: DataLoaderIniOption) -> str | bool:
    """Parse pytest INI option and perform additional validation if needed

    :param config: Pytest config
    :param option: INI option
    """
    try:
        v = config.getini(option)
        if option == DataLoaderIniOption.DATA_LOADER_DIR_NAME:
            if v.strip() in ("", ".", "..") or os.sep in v:
                raise ValueError(rf"Invalid value: '{v}'")
        return v
    except ValueError as e:
        raise pytest.UsageError(f"INI option {option}: {e}")


def is_valid_fixture_name(name: str) -> bool:
    """Check if the given name is valid as a fixture name

    :param name: The name to check
    """
    return name.isidentifier() and not keyword.iskeyword(name)


def generate_default_ids(
    loaded_data: Iterable[LoadedData | LazyLoadedData | LazyLoadedPartData], load_attrs: DataLoaderLoadAttrs
) -> Generator[str]:
    """Generate default param IDs for the loaded data"""
    if load_attrs.lazy_loading:
        return (repr(x) for x in loaded_data)
    else:
        if load_attrs.loader.requires_file_path and load_attrs.loader.requires_parametrization:
            return (repr(x.data) for x in loaded_data)
        else:
            return (x.file_name for x in loaded_data)


def get_num_func_args(f: Callable[..., Any]) -> int:
    """Returns number of arguments the function takes

    :param f: A function
    """
    sig = inspect.signature(f)
    return len(sig.parameters)


def bind_and_call_loader_func(
    loader_func: Callable[..., Any],
    file_path: Path,
    data: LoadedDataType | LazyLoadedData | LazyLoadedPartData | type[UnsupportedFuncArg],
) -> LoadedDataType:
    """Call a loader function with right arguments based on the function definition

    :param loader_func: Loader function to call
    :param file_path: Path to the loaded file
    :param data: Loaded data
    """
    if not callable(loader_func):
        raise TypeError(f"Loader function must be a callable, not {type(loader_func).__name__}")

    len_func_args = get_num_func_args(loader_func)
    max_allowed_args = 1 if data is UnsupportedFuncArg else 2
    if not 0 < len_func_args < max_allowed_args + 1:
        raise TypeError(
            f"Invalid loader function was provided. It supports up to {max_allowed_args} arguments. Got {len_func_args}"
        )

    if len_func_args == 2:
        return loader_func(file_path, data)
    else:
        if data is UnsupportedFuncArg:
            return loader_func(file_path)
        else:
            return loader_func(data)


@lru_cache
def resolve_relative_path(
    data_loader_dir_name: str,
    root_dir: Path,
    relative_path_to_search: Path,
    search_from: Path,
    /,
    *,
    is_file: bool,
) -> Path:
    """Locate the given relative file or directory path in the nearest data loader directory by searching upwards from
    the current location

    :param data_loader_dir_name: The data loader directory name
    :param root_dir: A root directory the path lookup should stop at
    :param relative_path_to_search: A file or directory path relative from a data loader directory
    :param search_from: A file or directory path to start searching from
    :param is_file: Whether the relative path is file or directory
    """
    assert root_dir.exists()
    assert search_from.exists()
    assert search_from.is_absolute() and search_from.is_relative_to(root_dir)

    loader_dirs = []
    if search_from.is_file():
        search_from = search_from.parent
    for dir_to_search in (search_from, *(search_from.parents)):
        loader_dir = dir_to_search / data_loader_dir_name
        if loader_dir.exists():
            loader_dirs.append(loader_dir)
            file_or_dir_path = loader_dir / relative_path_to_search
            if file_or_dir_path.exists():
                # Ignore if a directory with the same name as the required file (or vice versa) is found
                if (file_or_dir_path.is_file() and is_file) or (file_or_dir_path.is_dir() and not is_file):
                    return file_or_dir_path.resolve()

        if dir_to_search == root_dir:
            break

    if loader_dirs:
        listed_loader_dirs = "\n".join(f"  - {x}" for x in loader_dirs)
        err = (
            f"Unable to locate the specified {'file' if is_file else 'directory'} '{relative_path_to_search}' under "
            f"any of the following data loader directories:\n"
            f"{listed_loader_dirs}"
        )
    else:
        err = f"Unable to find any data loader directory '{data_loader_dir_name}'"
    raise FileNotFoundError(err)
