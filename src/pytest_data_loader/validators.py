from __future__ import annotations

import glob
import inspect
import warnings
from collections.abc import Callable, Iterable
from inspect import Parameter
from pathlib import Path
from typing import Any

from pytest import Mark, MarkDecorator

from pytest_data_loader.constants import ROOT_DIR
from pytest_data_loader.paths import check_circular_symlink, expand_env_vars, has_env_vars
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType, FileReadOptions, HashableDict, PytestMarkType
from pytest_data_loader.utils import get_max_allowed_loader_func_args, is_valid_fixture_name


def validate_loader_options(
    *,
    loader: DataLoader,
    fixture_names: Any,
    path: Any,
    lazy_loading: Any,
    recursive: bool,
    read_options: Any,
    reader: Any,
    onload_func: Any,
    parametrizer_func: Any,
    filter_func: Any,
    process_func: Any,
    reader_func: Any,
    read_options_func: Any,
    marks: Any,
    ids: Any,
) -> dict[str, Any]:
    """Validate loader options"""
    if not isinstance(lazy_loading, bool):
        raise TypeError(f"lazy_loading: Must be a boolean, but got {_get_type_name(lazy_loading)}")
    if not isinstance(recursive, bool):
        raise TypeError(f"recursive: Must be a boolean, but got {_get_type_name(recursive)}")

    if ids is not None and not (callable(ids) or isinstance(ids, Iterable)):
        # String value is intentionally allowed to match @pytest.mark.parametrize() behavior
        raise TypeError(f"ids: Must be a callable or an iterable, but got {_get_type_name(ids)}")

    validated_fixture_names = validate_fixture_names(fixture_names)
    validated_path = validate_path(path, loader=loader, recursive=recursive)

    # Note: We let pytest validate each mark/id value
    marker_func: Callable[..., PytestMarkType | None] | None
    if marks is None or (callable(marks) and not isinstance(marks, (MarkDecorator, Mark))):
        marker_func = marks
    else:
        marker_func = lambda _: marks  # noqa: E731

    id_func = ids_seq = None
    if callable(ids):
        id_func = ids
    elif isinstance(ids, Iterable):
        # Intentionally allowing a string value and ignoring empty IDs here to match the
        # current pytest.mark.parametrize() behavior
        ids_seq = tuple(ids) or None

    validate_reader(reader)
    validate_read_options(read_options)

    for loader_func, func_type in [
        (onload_func, DataLoaderFunctionType.ONLOAD_FUNC),
        (parametrizer_func, DataLoaderFunctionType.PARAMETRIZER_FUNC),
        (filter_func, DataLoaderFunctionType.FILTER_FUNC),
        (process_func, DataLoaderFunctionType.PROCESS_FUNC),
        (reader_func, DataLoaderFunctionType.READER_FUNC),
        (read_options_func, DataLoaderFunctionType.READ_OPTIONS_FUNC),
        (marker_func, DataLoaderFunctionType.MARKER_FUNC),
        (id_func, DataLoaderFunctionType.ID_FUNC),
    ]:
        validate_loader_func(loader_func, loader=loader, func_type=func_type)

    return dict(
        fixture_names=validated_fixture_names,
        path=validated_path,
        lazy_loading=lazy_loading,
        recursive=recursive,
        reader=reader,
        read_options=HashableDict(read_options or {}),
        onload_func=onload_func,
        parametrizer_func=parametrizer_func,
        filter_func=filter_func,
        process_func=process_func,
        reader_func=reader_func,
        read_options_func=read_options_func,
        marker_func=marker_func,
        id_func=id_func,
        ids=ids_seq,
    )


def validate_fixture_names(value: Any) -> tuple[str, ...]:
    """Validate and normalize the fixture_names argument.

    Accepts either a comma-separated string or a tuple of strings. Returns a
    normalized tuple of stripped identifier strings of length 1 or 2.

    :param value: Raw fixture_names as passed by the caller
    """
    if not isinstance(value, (str, tuple)):
        raise TypeError(f"fixture_names: Must be a string or tuple, but got {_get_type_name(value)}")
    if isinstance(value, tuple) and not all(isinstance(x, str) for x in value):
        raise TypeError(
            f"fixture_names: Must be a tuple of strings, but got {_get_type_name(value)} "
            f"with element types {[_get_type_name(v) for v in value]}."
        )

    if isinstance(value, str):
        normalized_names = tuple(x.strip() for x in value.split(","))
    else:
        normalized_names = tuple(value)

    err = "Invalid fixture_names value"
    if not all(is_valid_fixture_name(x) for x in normalized_names):
        raise ValueError(f"{err}: One or more values are illegal: {value!r}")

    len_names = len(normalized_names)
    if not 0 < len_names < 3:
        raise ValueError(f"{err}: It must be either 1 or 2 fixture names, but got {len_names}: {value!r}")

    return normalized_names


def validate_path(value: Any, *, loader: DataLoader, recursive: bool) -> Path | tuple[Path, ...]:
    """Validate and normalize the path argument.

    Accepts a single path (str or Path) or a sequence of paths. Returns a normalized Path for single-path input,
    or tuple[Path, ...] for multi-path input.

    :param value: Raw path value as passed by the caller
    :param loader: The data loader being configured; used for context-specific validation
    :param recursive: Whether recursive directory loading is requested; used to detect misconfigured glob patterns
    """
    if isinstance(value, list | tuple):
        if not loader.requires_parametrization:
            raise ValueError(f"Multi-path is not supported for @{loader.__name__} loader")
        if len(value) == 0:
            raise ValueError("path: Multi-path list must not be empty")
        if not all(isinstance(p, Path | str) for p in value):
            raise TypeError(
                f"path: Each path must a be a string or pathlib.Path object, but got "
                f"{[_get_type_name(p) for p in value]}"
            )
        result = []
        # NOTE: Do NOT use a comprehension here. It affects the stacklevel set in warnings.warn for Python < 3.12
        #       due to unsupported PEP 709
        for p in value:
            result.append(_validate_single_path(p, loader=loader, recursive=recursive))
        return tuple(result)
    else:
        if not isinstance(value, Path | str):
            raise TypeError(f"path: Must be a string or pathlib.Path object, but got {_get_type_name(value)}")
        return _validate_single_path(value, loader=loader, recursive=recursive)


def _validate_single_path(path: Path | str, *, loader: DataLoader, recursive: bool) -> Path:
    """Validate a single path value.

    :param path: The path to validate
    :param loader: The data loader being configured
    :param recursive: Whether recursive directory loading is requested
    """
    if has_env_vars(path):
        path = expand_env_vars(path)
    path_ = Path(path)
    if path_ in (Path("."), Path(".."), Path(ROOT_DIR)):
        raise ValueError(f"Invalid path value: {str(path)!r}")
    if glob.has_magic(str(path_)):
        if not loader.requires_parametrization:
            raise ValueError(f"@{loader.__name__} loader does not support glob pattern: {str(path)!r}")
        if recursive is True and "**" not in str(path_):
            warnings.warn(
                f"The 'recursive' option is ignored for the glob pattern {str(path)!r}. Use '**' in the pattern to "
                f"enable recursive matching",
                UserWarning,
                stacklevel=6,  # The @parametrize_dir(...) def in the test
            )
    elif path_.is_absolute():
        # NOTE: The existence of the path is checked later to handle the error based on the on_missing option.
        if path_.is_symlink():
            check_circular_symlink(path_)
        if path_.is_dir() and loader.is_file_loader:
            raise ValueError(f"Invalid path type: @{loader.__name__} loader must take a file path, not {str(path)!r}")
        if path_.is_file() and not loader.is_file_loader:
            raise ValueError(
                f"Invalid path type: @{loader.__name__} loader must take a directory path, not {str(path)!r}"
            )
    return path_


def validate_loader_func(loader_func: Any, *, loader: DataLoader, func_type: DataLoaderFunctionType) -> int | None:
    """Validate the loader function definition. Returns the defined function arg count on success.

    :param loader_func: Loader function
    :param loader: The loader loader_func is associated with
    :param func_type: Type of the loader function
    """

    if loader_func is None:
        return None
    if not callable(loader_func):
        raise TypeError(f"{func_type.public_name}: Must be a callable, but got {_get_type_name(loader_func)}")

    try:
        sig = inspect.signature(loader_func)
    except ValueError as e:
        raise ValueError(f"Unsupported '{func_type.public_name}' callable definition: {loader_func!r}") from e

    parameters = sig.parameters

    has_var_positional = any(p.kind == Parameter.VAR_POSITIONAL for p in parameters.values())
    positional_kinds = (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
    num_explicit = sum(1 for p in parameters.values() if p.kind in positional_kinds)

    max_allowed_args = get_max_allowed_loader_func_args(loader, func_type)
    err = None
    if not all(p.kind in (*positional_kinds, Parameter.VAR_POSITIONAL) for p in parameters.values()):
        err = "Only positional arguments are allowed"
    elif (has_var_positional and num_explicit > max_allowed_args) or (
        not has_var_positional and not 0 < num_explicit < max_allowed_args + 1
    ):
        if max_allowed_args == 1:
            err = "It must take only 1 argument (file path)."
        else:
            err = f"It must take up to {max_allowed_args} arguments."
        err += f" Got {num_explicit}"

    if err:
        raise TypeError(f"Detected invalid '{func_type.public_name}' callable definition. {err}")

    return max_allowed_args if has_var_positional else num_explicit


def validate_reader(reader: Any) -> None:
    """Validate the reader

    :param reader: File reader passed by the caller
    """
    if reader is None:
        return
    if not ((isinstance(reader, type) and issubclass(reader, Iterable)) or callable(reader)):
        raise TypeError(f"reader: Must be an iterable or a callable, but got {_get_type_name(reader)}")


def validate_read_options(read_options: Any) -> None:
    """Validate the read_options argument

    :param read_options: Read options passed by the caller
    """
    if read_options is None:
        return
    if not isinstance(read_options, dict):
        raise TypeError(f"read_options: Must be a dict, but got {_get_type_name(read_options)}")
    if unsupported := set(read_options.keys()).difference(set(FileReadOptions.__annotations__.keys())):
        raise ValueError(f"read_options: Unsupported read options: {', '.join(unsupported)}")
    if (mode := read_options.get("mode")) and mode not in ("r", "rt", "rb"):
        raise ValueError(f"read_options: Invalid read mode: {mode}")


def _get_type_name(val: Any) -> str:
    t = val if isinstance(val, type) else type(val)
    return t.__name__
