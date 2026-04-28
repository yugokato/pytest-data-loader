from __future__ import annotations

import ast
import inspect
import keyword
import sys
from collections.abc import Callable
from functools import lru_cache, wraps
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


def get_data_loader_source(test_func: Callable[..., Any], position: int, data_loader_name: str) -> str | None:
    """Return the source text of the *position*-th data loader decorator on the test function.

    Parses the test function's source file, resolves which names refer to ``pytest_data_loader`` decorators (via the
    file's top-level imports), and locates the decorator at the requested position among the data loader decorators
    actually applied to the function. The returned text is the exact source segment of the decorator call, prefixed
    with @. When the segment spans multiple lines, internal whitespace is collapsed to a single space.

    :param test_func: The test function carrying stacked data loader decorators
    :param position: 0-indexed position in source order (topmost data loader decorator is 0)
    :param data_loader_name: Expected data loader name at that position. Used as a sanity check to guard against
                             import-resolution edge cases
    """
    try:
        source_file = inspect.getsourcefile(test_func)
        if source_file is None:
            return None
        with open(source_file, encoding="utf-8") as f:
            file_source = f.read()
        tree = ast.parse(file_source)
    except Exception:
        return None

    code = getattr(test_func, "__code__", None)
    func_lineno: int | None = code.co_firstlineno if code is not None else None
    func_node = _find_func_node(tree, test_func.__name__, func_lineno)
    if func_node is None:
        return None

    direct_names, module_aliases = _resolve_data_loader_imports(tree)
    matching: list[tuple[ast.Call, str]] = []
    for decorator in func_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        canonical = _resolve_data_loader_name(decorator, direct_names, module_aliases)
        if canonical is not None:
            matching.append((decorator, canonical))
    if position >= len(matching):
        return None

    chosen, chosen_canonical = matching[position]
    if chosen_canonical != data_loader_name:
        return None

    segment = ast.get_source_segment(file_source, chosen)
    if segment is None:
        return None
    if "\n" in segment:
        segment = " ".join(segment.split())
    return f"@{segment}"


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


@lru_cache
def get_data_loader_names() -> list[str]:
    import pytest_data_loader.loaders.loaders as loaders

    data_loader_names = []
    for attr in dir(loaders):
        obj = getattr(loaders, attr)
        if getattr(obj, "is_data_loader", None) is True:
            data_loader_names.append(obj.__name__)
    assert data_loader_names
    return data_loader_names


def _find_func_node(tree: ast.Module, name: str, lineno: int | None) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Locate the FunctionDef / AsyncFunctionDef node matching *name*, using *lineno* as a tie-breaker.

    :param tree: Parsed AST of the source file
    :param name: The function name to search for
    :param lineno: Line number of the ``def`` keyword (``co_firstlineno``); used only when multiple same-named
                   functions exist in the file
    :return: The matching function node, or ``None`` if not found
    """
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if not candidates:
        return None
    if lineno is not None:
        for node in candidates:
            if node.lineno == lineno:
                return node
    return candidates[0]


def _resolve_data_loader_imports(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """Walk top-level imports to determine which names refer to ``pytest_data_loader`` decorators.

    :param tree: Parsed AST of the source file
    :return: A tuple ``(direct_names, module_aliases)``:
             - ``direct_names``: maps a local name to its canonical loader name. Populated from
               ``from pytest_data_loader import <loader> [as <alias>]``
             - ``module_aliases``: set of names that refer to the ``pytest_data_loader`` package itself.
               Populated from ``import pytest_data_loader [as <alias>]``
    """
    package = __package__.split(".")[0]
    loader_names = set(get_data_loader_names())
    direct_names: dict[str, str] = {}
    module_aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == package:
            for alias in node.names:
                if alias.name == "*":
                    for name in loader_names:
                        direct_names[name] = name
                elif alias.name in loader_names:
                    direct_names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package:
                    module_aliases.add(alias.asname or alias.name)
    return direct_names, module_aliases


def _resolve_data_loader_name(call: ast.Call, direct_names: dict[str, str], module_aliases: set[str]) -> str | None:
    """Return the canonical loader name if ``call`` is a data loader decorator, else ``None``.

    :param call: An AST Call node representing a decorator
    :param direct_names: Local-name to canonical-loader-name mapping from ``from pytest_data_loader import …``
    :param module_aliases: Names that refer to the ``pytest_data_loader`` package itself
    """
    func = call.func
    if isinstance(func, ast.Name):
        return direct_names.get(func.id)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id in module_aliases and func.attr in get_data_loader_names():
            return func.attr
    return None
