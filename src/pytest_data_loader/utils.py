from __future__ import annotations

import inspect
import keyword
import sys
from collections.abc import Callable
from functools import wraps
from inspect import Parameter
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from pytest_data_loader.types import DataLoaderFunctionType

R = TypeVar("R")
P = ParamSpec("P")


def is_valid_fixture_name(name: str) -> bool:
    """Check if the given name is valid as a fixture name

    :param name: The name to check
    """
    return name.isidentifier() and not keyword.iskeyword(name)


def validate_loader_func_args_and_normalize(
    loader_func: Callable[..., Any], func_type: DataLoaderFunctionType | None = None, with_file_path_only: bool = False
) -> Callable[..., Any]:
    """Validates the loader function definition and returns a normalized function that can take 2 arguments but call
    the original function it with the right argument(s)

    :param loader_func: Loader function
    :param func_type: Loader function type
    :param with_file_path_only: The loader function must take only file path
    """

    def inject_error_context(file_path: Path) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Inject error context to a loader function call"""

        def decorator(f: Callable[P, R]) -> Callable[P, R]:
            @wraps(f)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    err = f"Error while processing {func_type} for '{file_path.name}' ({file_path})"
                    add_error_note(e, err)
                    raise

            return wrapper

        return decorator

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
        return wraps(loader_func)(lambda file_path, data: inject_error_context(file_path)(loader_func)(file_path, data))
    elif with_file_path_only:
        return wraps(loader_func)(lambda file_path, *_: inject_error_context(file_path)(loader_func)(file_path))
    else:
        return wraps(loader_func)(lambda file_path, data: inject_error_context(file_path)(loader_func)(data))


def add_error_note(exc: Exception, note: str) -> None:
    """Add a contextual note to an exception.

    On Python 3.11+, uses the built-in ``add_note()`` method.
    On Python 3.10, appends the note to the exception's args when possible.

    :param exc: The exception to annotate
    :param note: The note to add
    """
    if sys.version_info >= (3, 11):
        exc.add_note(note)
    elif len(exc.args) == 1 and isinstance(exc.args[0], str):
        exc.args = (f"{exc.args[0]}\n{note}",)
