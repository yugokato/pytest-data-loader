import inspect
import keyword
import os
import re
from collections.abc import Callable, Collection
from functools import lru_cache, wraps
from inspect import Parameter
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark import ParameterSet
from pytest import Config, Mark, MarkDecorator

from pytest_data_loader.types import (
    DataLoaderFunctionType,
    DataLoaderIniOption,
    DataLoaderLoadAttrs,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
)


@lru_cache
def parse_ini_option(config: Config, option: DataLoaderIniOption) -> str | bool | Path:
    """Parse pytest INI option and perform additional validation if needed

    :param config: Pytest config
    :param option: INI option
    """
    try:
        v = config.getini(option)
        if option == DataLoaderIniOption.DATA_LOADER_DIR_NAME:
            assert isinstance(v, str)
            if v in ("", ".", "..") or os.sep in v:
                raise ValueError(rf"Invalid value: '{v}'")
        elif option == DataLoaderIniOption.DATA_LOADER_ROOT_DIR:
            assert isinstance(v, str)
            orig_value = v
            pytest_rootdir = config.rootpath
            if v == "":
                return pytest_rootdir
            if has_env_vars(v):
                v = os.path.expandvars(v)
                if has_env_vars(v):
                    raise ValueError(f"Unable to resolve environment variable(s) in the path: {v!r}")
            v = Path(os.path.expanduser(v))
            if not v.is_absolute():
                v = v.resolve()

            err = None
            if not v.exists():
                err = "The specified path does not exist"
            elif v.is_file():
                err = "The path must be a directory"
            elif not pytest_rootdir.is_relative_to(v):
                err = "The path must be one of the parent directories of pytest rootdir"
            elif v.is_relative_to(pytest_rootdir):
                err = "The path must be outside the pytest rootdir"
            if err:
                err += f": {orig_value!r}"
                if orig_value != str(v):
                    err += f" (resolved value: {str(v)!r})"
                raise ValueError(err)
        return v
    except ValueError as e:
        raise pytest.UsageError(f"INI option {option}: {e}")


def is_valid_fixture_name(name: str) -> bool:
    """Check if the given name is valid as a fixture name

    :param name: The name to check
    """
    return name.isidentifier() and not keyword.iskeyword(name)


def has_env_vars(path: str) -> bool:
    """Check if the path contains environment variables ($VAR, ${VAR}, or %VAR%)

    :param path: The path to check
    """
    pattern = r"(\$[A-Za-z_]\w*|\${[A-Za-z_]\w*}|%[A-Za-z_]\w*%)"
    return bool(re.search(pattern, path))


def generate_parameterset(
    load_attrs: DataLoaderLoadAttrs, loaded_data: LoadedData | LazyLoadedData | LazyLoadedPartData
) -> ParameterSet:
    """Generate Pytest ParameterSet object for the loaded data

    :param load_attrs: The load attributes
    :param loaded_data: The loaded data
    """

    def generate_param_id() -> Any:
        if load_attrs.id_func is None:
            if load_attrs.lazy_loading:
                return repr(loaded_data)
            else:
                if load_attrs.loader.requires_file_path and load_attrs.loader.requires_parametrization:
                    return repr(loaded_data.data)
                else:
                    return loaded_data.file_name
        else:
            if isinstance(loaded_data, LazyLoadedPartData):
                # When id_func is provided for the @parametrize loader, parameter ID is generated when
                # LazyLoadedPartData is created
                return loaded_data.meta["id"] or repr(loaded_data)
            return load_attrs.id_func(loaded_data.file_path, loaded_data.data)

    def generate_param_marks() -> MarkDecorator | Collection[MarkDecorator | Mark]:
        default_markers = ()
        if load_attrs.marker_func is None:
            return default_markers
        else:
            assert load_attrs.loader.requires_parametrization
            if isinstance(loaded_data, LazyLoadedPartData):
                # When marker_func is provided for the @parametrize loader, marks are generated when
                # LazyLoadedPartData is created
                marks = loaded_data.meta["marks"]
            else:
                func_args: tuple[Any, ...]
                if load_attrs.loader.requires_file_path:
                    func_args = (loaded_data.file_path, loaded_data.data)
                else:
                    func_args = (loaded_data.file_path,)
                marks = load_attrs.marker_func(*func_args)
            return marks or default_markers

    args: tuple[Any, ...]
    if load_attrs.requires_file_path:
        args = (loaded_data.file_path, loaded_data.data)
    else:
        args = (loaded_data.data,)
    try:
        return pytest.param(*args, marks=generate_param_marks(), id=generate_param_id())
    finally:
        if isinstance(loaded_data, LazyLoadedPartData):
            loaded_data.meta.clear()


def validate_loader_func_args_and_normalize(
    loader_func: Callable[..., Any], func_type: DataLoaderFunctionType | None = None, with_file_path_only: bool = False
) -> Callable[..., Any]:
    """Validates the loader function definition and returns a normalized function that can take 2 arguments but call
    the original function it with the right argument(s)

    :param loader_func: Loader function
    :parma func_type: Loader function type
    :param with_file_path_only: The loader function must take only file path
    """
    try:
        sig = inspect.signature(loader_func)
    except ValueError as e:
        raise ValueError(f"Unsupported loader_func: {loader_func!r}") from e

    parameters = sig.parameters
    len_func_args = len(parameters)

    max_allowed_args = 1 if with_file_path_only else 2
    err = None
    if not 0 < len_func_args < max_allowed_args + 1:
        err = f"It must take up to {max_allowed_args} arguments. Got {len_func_args}"
    elif not all(p.kind == Parameter.POSITIONAL_OR_KEYWORD for p in parameters.values()):
        err = "Only positional arguments are allowed"
    if err:
        f_type = f"{func_type} " if func_type else ""
        raise TypeError(f"Detected invalid {f_type}loader function definition. {err}")

    if len_func_args == 2:
        return wraps(loader_func)(lambda file_path, data: loader_func(file_path, data))
    elif with_file_path_only:
        return wraps(loader_func)(lambda file_path, *_: loader_func(file_path))
    else:
        return wraps(loader_func)(lambda _, data: loader_func(data))


@lru_cache
def resolve_relative_path(
    data_loader_dir_name: str,
    data_loader_root_dir: Path,
    relative_path_to_search: Path,
    search_from: Path,
    /,
    *,
    is_file: bool,
) -> Path:
    """Locate the given relative file or directory path in the nearest data loader directory by searching upwards from
    the current location

    :param data_loader_dir_name: The data loader directory name
    :param data_loader_root_dir: A root directory the path lookup should stop at
    :param relative_path_to_search: A file or directory path relative from a data loader directory
    :param search_from: A file or directory path to start searching from
    :param is_file: Whether the relative path is file or directory
    """
    assert data_loader_root_dir.is_absolute()
    assert data_loader_root_dir.exists()
    assert search_from.exists()
    assert search_from.is_absolute()
    if not search_from.is_relative_to(data_loader_root_dir):
        raise ValueError(f"The test file location {search_from} is not in the subpath of {data_loader_root_dir}")

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

        if dir_to_search == data_loader_root_dir:
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
