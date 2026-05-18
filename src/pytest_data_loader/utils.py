from __future__ import annotations

import ast
import codecs
import inspect
import keyword
import sys
from collections.abc import Callable
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from pytest_data_loader.types import DataLoader, DataLoaderFunctionType, DataLoaderType

R = TypeVar("R")
P = ParamSpec("P")


def is_valid_fixture_name(name: str) -> bool:
    """Check if the given name is valid as a fixture name

    :param name: The name to check
    """
    return name.isidentifier() and not keyword.iskeyword(name)


@lru_cache
def get_max_allowed_loader_func_args(loader: DataLoader, func_type: DataLoaderFunctionType) -> int:
    """Return the maximum number of positional arguments allowed for the given loader function type.

    :param loader: The data loader the function is associated with
    :param func_type: Type of the loader function
    """
    if loader.type == DataLoaderType.PARAMETRIZE_DIR:
        # @parametrize_dir
        if func_type == DataLoaderFunctionType.FILTER_FUNC:
            # (path)
            return 1
        elif func_type == DataLoaderFunctionType.PROCESS_FUNC:
            # (idx, path, data)
            return 3
        else:
            # (idx, path)
            return 2
    else:
        # @load or @parametrize
        if loader.type == DataLoaderType.PARAMETRIZE and func_type in (
            DataLoaderFunctionType.MARKER_FUNC,
            DataLoaderFunctionType.ID_FUNC,
            DataLoaderFunctionType.PROCESS_FUNC,
        ):
            # (idx, path, data)
            return 3
        else:
            # (path, data)
            return 2


def normalize_loader_func(
    loader: DataLoader,
    loader_func: Callable[..., Any],
    func_type: DataLoaderFunctionType,
    *,
    num_defined_args: int | None = None,
) -> Callable[..., Any]:
    """Normalize the given loader function to a standard signature and inject error context on exceptions.

    :param loader: The data loader the function is associated with
    :param loader_func: The pre-validated loader function to normalize
    :param func_type: Type of the loader function
    :param num_defined_args: Parameter count of loader_func. When provided, the signature inspection is skipped
    """

    def inject_error_context(file_path: Path) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Inject error context to a loader function call"""

        def decorator(f: Callable[P, R]) -> Callable[P, R]:
            @wraps(f)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    err = (
                        f"Error while processing '{func_type.public_name}' callable for "
                        f"'{file_path.name}' ({file_path})"
                    )
                    add_error_note(e, err)
                    raise

            return wrapper

        return decorator

    if num_defined_args is None:
        from pytest_data_loader.validators import validate_loader_func

        num_defined_args = validate_loader_func(loader_func, loader=loader, func_type=func_type)

    max_allowed_args = get_max_allowed_loader_func_args(loader, func_type)
    no_data_arg = loader.type == DataLoaderType.PARAMETRIZE_DIR and func_type != DataLoaderFunctionType.PROCESS_FUNC
    supports_idx = (no_data_arg and max_allowed_args >= 2) or (not no_data_arg and max_allowed_args >= 3)

    @wraps(loader_func)
    def normalized_func_with_idx(idx: int, file_path: Path, data: Any) -> Any:
        wrapped = inject_error_context(file_path)(loader_func)
        if no_data_arg:
            if num_defined_args == 2:
                return wrapped(idx, file_path)
            else:
                return wrapped(file_path)
        else:
            if num_defined_args == 3:
                return wrapped(idx, file_path, data)
            elif num_defined_args == 2:
                return wrapped(file_path, data)
            else:
                return wrapped(data)

    @wraps(loader_func)
    def normalized_func_without_idx(file_path: Path, data: Any) -> Any:
        wrapped = inject_error_context(file_path)(loader_func)
        if num_defined_args == 2:
            return wrapped(file_path, data)
        elif max_allowed_args == 1:
            return wrapped(file_path)
        else:
            return wrapped(data)

    if supports_idx:
        return normalized_func_with_idx
    else:
        return normalized_func_without_idx


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

    On Python 3.11+, uses ``Exception.add_note()``.
    On older versions, stores notes in ``__notes__``.
    """
    if sys.version_info >= (3, 11):
        exc.add_note(note)
    else:
        # Best-effort compatibility for older Python versions
        notes = getattr(exc, "__notes__", None)
        if not isinstance(notes, list):
            notes = []
        notes.append(note)

        try:
            setattr(exc, "__notes__", notes)
        except Exception:
            pass


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


def can_decode(chunk: bytes, encoding: str) -> bool:
    """Return True if chunk can be decoded with encoding, tolerating trailing partial multibyte sequences."""
    try:
        codecs.getincrementaldecoder(encoding)().decode(chunk, final=False)
        return True
    except UnicodeDecodeError:
        return False
