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
            if load_attrs.lazy_loading or not (
                load_attrs.loader.is_file_loader and load_attrs.loader.requires_parametrization
            ):
                return repr(loaded_data)
            else:
                return repr(loaded_data.data)
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
                if load_attrs.loader.is_file_loader:
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
    elif not all(p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD) for p in parameters.values()):
        err = "Only positional arguments are allowed"
    if err:
        f_type = f"{func_type} " if func_type else ""
        raise TypeError(f"Detected invalid {f_type}loader function definition. {err}")

    if len_func_args == 2:
        return wraps(loader_func)(lambda file_path, data: loader_func(file_path, data))  # noqa: PLW0108
    elif with_file_path_only:
        return wraps(loader_func)(lambda file_path, *_: loader_func(file_path))
    else:
        return wraps(loader_func)(lambda _, data: loader_func(data))
