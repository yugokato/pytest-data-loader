from __future__ import annotations

import bz2
import errno
import glob
import gzip
import lzma
import os
import re
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import IO, Any, BinaryIO, Literal, TextIO, cast, overload

from pytest_data_loader.compat import Self
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.utils import add_error_note

_COMPRESSION_OPENERS: dict[str, Callable[..., IO[Any]]] = {
    ".gz": gzip.open,
    ".bz2": bz2.open,
    ".xz": lzma.open,
}
SUPPORTED_COMPRESSION_EXTENSIONS: tuple[str, ...] = tuple(_COMPRESSION_OPENERS)


@lru_cache
def resolve_relative_path(
    data_loader_dir_name: str,
    data_loader_root_dir: Path,
    relative_path_to_search: Path,
    search_from: Path,
    /,
    *,
    is_file: bool,
) -> tuple[Path, tuple[Path, ...]]:
    """Locate the given relative file or directory path in the nearest data directory by searching upwards from the
    current location

    :param data_loader_dir_name: The data directory name
    :param data_loader_root_dir: A root directory the path lookup should stop at
    :param relative_path_to_search: A file or directory path relative from a data loader directory.
           This can be a glob pattern
    :param search_from: A file or directory path to start searching from
    :param is_file: Whether the provided path is for a file or directory
    """
    is_glob = glob.has_magic(str(relative_path_to_search))
    assert data_loader_root_dir.is_absolute()
    assert data_loader_root_dir.exists()
    assert not relative_path_to_search.is_absolute()
    assert search_from.exists()
    assert search_from.is_absolute()
    if not search_from.is_relative_to(data_loader_root_dir):
        raise ValueError(f"The test file location {search_from} is not in the subpath of {data_loader_root_dir}")

    data_dirs = []
    if search_from.is_file():
        search_from = search_from.parent
    for dir_to_search in (search_from, *search_from.parents):
        data_dir = dir_to_search / data_loader_dir_name
        if data_dir.exists():
            data_dirs.append(data_dir.relative_to(data_loader_root_dir.parent))

            # Note: Even if the path looks like a glob pattern, we check it as a literal path first in case it
            #       actually exists
            file_or_dir_path = data_dir / relative_path_to_search
            if os.path.lexists(file_or_dir_path):  # equivalent to Path.exists(follow_symlinks=False) for Python <3.12
                if file_or_dir_path.is_symlink():
                    check_circular_symlink(file_or_dir_path)
                # Ignore if a directory with the same name as the required file (or vice versa) is found
                if (file_or_dir_path.is_file() and is_file) or (file_or_dir_path.is_dir() and not is_file):
                    return data_dir, (file_or_dir_path,)

            if is_glob:
                matched = get_matching_paths(data_dir, str(relative_path_to_search), "file" if is_file else "directory")
                if matched:
                    return data_dir, matched

        if dir_to_search == data_loader_root_dir:
            break

    if data_dirs:
        if is_glob:
            err = f"Glob pattern {str(relative_path_to_search)!r} matched no {'files' if is_file else 'directories'}"
        else:
            err = f"Unable to locate the {'file' if is_file else 'directory'} {str(relative_path_to_search)!r}"
        if len(data_dirs) == 1:
            err += f" under data directory {str(data_dirs[0])!r}"
        else:
            listed_data_dirs = "\n".join(f"  - {x}" for x in data_dirs)
            err += f" under any of the following data directories:\n{listed_data_dirs}"
    else:
        err = f"Unable to find any data directory '{data_loader_dir_name}'"
    raise DataNotFound(err)


def get_matching_paths(root_dir: Path, pattern: str, match_type: Literal["file", "directory"]) -> tuple[Path, ...]:
    """Wrap glob.glob() and detect directory traversal cycles caused by symlinks.

    :param root_dir: The root directory path to glob from
    :param pattern: The glob pattern (relative to root_dir)
    :param match_type: The type of paths to return
    """
    if not root_dir.is_absolute():
        raise ValueError("root_dir must be an absolute path")

    is_file = match_type == "file"
    is_dir = match_type == "directory"
    visited_dirs: set[tuple[int, int]] = set()
    paths = glob.glob(pattern, root_dir=root_dir, recursive=True)  # hidden files/dirs will be excluded by default
    matched_paths: list[Path] = []
    for path in sorted(paths):
        p = root_dir / path
        if p.is_symlink():
            check_circular_symlink(p)
        if (is_file and p.is_file()) or (is_dir and p.is_dir()):
            if p.is_dir():
                check_and_track_dir(p, visited_dirs)
            matched_paths.append(p)
    return tuple(matched_paths)


def has_env_vars(path: Path | str) -> bool:
    """Check if the path contains environment variables ($VAR, ${VAR}, or %VAR%)

    :param path: The path to check
    """
    pattern = r"(\$[A-Za-z_]\w*|\${[A-Za-z_]\w*}|%[A-Za-z_]\w*%)"
    return bool(re.search(pattern, str(path)))


def expand_env_vars(value: Path | str) -> str:
    """Expand environment variables in the given path-like value.

    :param value: The path value possibly containing env-var references
    """
    expanded = os.path.expandvars(str(value))
    if has_env_vars(expanded):
        raise ValueError(f"Unable to resolve environment variable(s) in the path: {expanded!r}")
    return expanded


def check_circular_symlink(path: Path) -> None:
    """Detect a circular symlink resolution loops (ELOOP)

    :param path: The path to check
    """
    if path.is_symlink():
        try:
            path.resolve(strict=True)
        except (OSError, RuntimeError) as e:
            if (
                # Python < 3.13
                (isinstance(e, RuntimeError) and "symlink loop" in str(e).lower())
                # Unix
                or (isinstance(e, OSError) and e.errno == errno.ELOOP)
                # Windows (ERROR_CANT_RESOLVE_FILENAME)
                or (isinstance(e, OSError) and getattr(e, "winerror", None) == 1921)
            ):
                raise RuntimeError(f"Detected a circular symlink: {path}")
            raise


def check_and_track_dir(dir_path: Path, visited: set[tuple[int, int]]) -> None:
    """Record the directory's inode in visited, raising RuntimeError if it was already seen.

    :param dir_path: The directory whose inode should be tracked
    :param visited: Running set of (dev, ino) pairs for the current traversal
    """
    st = dir_path.stat()
    inode = (st.st_dev, st.st_ino)
    if inode in visited:
        raise RuntimeError(f"Detected a circular symlink: {dir_path}")
    visited.add(inode)


def split_glob_path(path: Path) -> tuple[Path, str]:
    """Split an absolute glob path into a literal base directory and a relative glob pattern.

    The base is the deepest directory that contains no wildcards, stopping one level above the
    first wildcard component. The pattern includes the first wildcard component and its parent directory.

    Example:
        '/a/b/dir/**'  → (Path('/a/b'), 'dir/**')

    :param path: An absolute path containing at least one wildcard component
    """
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    if not glob.has_magic(str(path)):
        raise ValueError("path must contain a wildcard")

    parts = path.parts
    # parts[0] is always the anchor (e.g. '/' or 'C:\\'), which never contains magic chars,
    # so magic_idx is always >= 1 for absolute paths.
    magic_idx = next((i for i, part in enumerate(parts) if glob.has_magic(part)))
    # Stop the base one level before the first wildcard so that the literal parent of the
    # wildcard stays in the pattern (e.g. 'dir/**' instead of just '**'). This ensures the same
    # glob semantics as if the full path were searched from root, and avoids anchoring at '/'.
    split = max(magic_idx - 1, 1)  # always keep at least the anchor in the base
    base = Path(*parts[:split])
    pattern = str(Path(*parts[split:]))
    return base, pattern


def is_compressed_path(path: Path) -> bool:
    """Return whether the given path is a supported compressed file (.gz/.bz2/.xz).

    :param path: File path to inspect
    """
    return path.suffix.lower() in SUPPORTED_COMPRESSION_EXTENSIONS


def get_effective_suffix(path: Path) -> str:
    """Return the format-bearing suffix of path, skipping a trailing compression suffix when present.

    :param path: File path to inspect

    Examples:
        Path("data.json.gz") -> ".json"
        Path("data.csv.bz2") -> ".csv"
        Path("data.json")    -> ".json"
        Path("data.gz")      -> ".gz"   (no inner suffix to expose)
    """
    suffixes = path.suffixes
    if len(suffixes) >= 2 and is_compressed_path(path):
        return suffixes[-2]
    return path.suffix


@overload
def compression_aware_open(path: Path, *, mode: Literal["r", "rt", "w", "wt", "a", "at"], **kwargs: Any) -> TextIO: ...


@overload
def compression_aware_open(path: Path, *, mode: Literal["rb", "wb", "ab"], **kwargs: Any) -> BinaryIO: ...


@overload
def compression_aware_open(path: Path, **kwargs: Any) -> TextIO: ...


def compression_aware_open(path: Path, **kwargs: Any) -> IO[Any]:
    """Open a file via `_compression_aware_open`, typed as a file handle.

    :param path: File path to open
    :param kwargs: Keyword arguments forwarded to the opener
    """
    return cast(IO[Any], _CompressionAwareOpen(path, **kwargs))


class _CompressionAwareOpen:
    """Open a file, routing through gzip/bz2/lzma openers when the suffix matches.

    Works as both a plain callable returning a file-like handle and as a context manager,
    mirroring the semantics of the builtin :func:`open`.

    For compression openers ``"r"`` means binary. This class normalizes the mode so that
    ``"r"`` and ``"rt"`` both produce a text-mode stream, matching builtin ``open()``.

    :param path: File path to open
    :param kwargs: Keyword arguments forwarded to the opener
    """

    def __init__(self, path: Path, **kwargs: Any) -> None:
        self._path = path
        self._encoding: str | None = kwargs.get("encoding")
        opener = _COMPRESSION_OPENERS.get(path.suffix.lower())
        if opener is None:
            opener = open
        else:
            # Normalize compressed "r" to text mode for consistency with builtin open()
            mode = kwargs.get("mode") or "r"
            if mode in ("r", "rt"):
                kwargs["mode"] = "rt"
        self._read_options = kwargs
        self._file: IO[Any] = opener(path, **kwargs)

    def _with_decode_error_context(self, f: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except UnicodeDecodeError as e:
            note = f"While reading {str(self._path)!r}"
            if self._read_options:
                options = ", ".join(f"{k}={v!r}" for k, v in self._read_options.items())
                note += f" with options: {options}"
            add_error_note(e, note)
            raise

    def read(self, *args: Any, **kwargs: Any) -> Any:
        return self._with_decode_error_context(self._file.read, *args, **kwargs)

    def readline(self, *args: Any, **kwargs: Any) -> Any:
        return self._with_decode_error_context(self._file.readline, *args, **kwargs)

    def readlines(self, *args: Any, **kwargs: Any) -> list[Any]:
        return self._with_decode_error_context(self._file.readlines, *args, **kwargs)

    def __next__(self) -> Any:
        return self._with_decode_error_context(self._file.__next__)

    def __iter__(self) -> Iterator[Any]:
        return self

    def __enter__(self) -> Self:
        self._file.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._file.__exit__(*args)

    def __getattr__(self, name: str) -> Any:
        if name == "_file":
            raise AttributeError(name)
        return getattr(self._file, name)
