from __future__ import annotations

import glob
import logging
import os
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from functools import cached_property, partial, wraps
from io import StringIO
from itertools import count
from pathlib import Path
from types import ModuleType
from typing import IO, Any, ClassVar, Concatenate, Literal, ParamSpec, TypeVar

from pytest_data_loader.constants import DEFAULT_ENCODING, PYTEST_DATA_LOADER_MODULE_CACHE
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.loaders.cache import CacheKey, ReadModeKey, SessionFileCache
from pytest_data_loader.loaders.reader import FileReader
from pytest_data_loader.paths import (
    check_and_track_dir,
    check_circular_symlink,
    compression_aware_open,
    get_effective_suffix,
    get_matching_paths,
    is_compressed_path,
    resolve_relative_path,
    split_glob_path,
)
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderFunctionType,
    DataLoaderLoadAttrs,
    DataLoaderOption,
    DataLoaderType,
    HashableDict,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
)
from pytest_data_loader.utils import can_decode, normalize_loader_func
from pytest_data_loader.validators import validate_read_options, validate_reader

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T", bound="Loader")

logger = logging.getLogger(__name__)


def loader(f: Callable[P, R]) -> Callable[P, R]:
    """Decorator to register a decorated function as a data loader"""
    f.is_data_loader = True  # type: ignore[attr-defined]
    f.type = DataLoaderType(f.__name__)  # type: ignore[attr-defined]
    f.is_file_loader = f.type in [DataLoaderType.LOAD, DataLoaderType.PARAMETRIZE]  # type: ignore[attr-defined]
    f.requires_parametrization = f.type in [DataLoaderType.PARAMETRIZE, DataLoaderType.PARAMETRIZE_DIR]  # type: ignore[attr-defined]
    f.should_split_data = f.type == DataLoaderType.PARAMETRIZE  # type: ignore[attr-defined]
    return f


def create_loaders(
    path: Path,
    load_attrs: DataLoaderLoadAttrs,
    data_loader_option: DataLoaderOption,
    *,
    file_cache: SessionFileCache | None = None,
    gidx_counter: count[int] | None = None,
) -> list[FileLoader | DirectoryLoader]:
    """Resolve a single path entry (which may be a glob pattern or a concrete path) to file or directory loaders.
    Returns one loader per matched entry (possibly many when *path* is a glob pattern).

    :param path: A single path entry from the data loader's path argument. This can be a glob pattern
    :param load_attrs: Loader attributes for the current data loader
    :param data_loader_option: Data loader options
    :param file_cache: Session-scoped file cache. None disables session caching
    :param gidx_counter: Global index counter that produces continuous post-filter idx values across all loaders
                         created for a single decorator invocation
    """
    strip_trailing_whitespace = bool(data_loader_option.strip_trailing_whitespace)
    default_encoding = str(data_loader_option.default_encoding)
    is_file = load_attrs.loader.is_file_loader
    is_glob = glob.has_magic(str(path))

    if path.is_absolute():
        data_dir_path = None
        if is_glob:
            if os.path.lexists(path):  # equivalent to Path.exists(follow_symlinks=False) for Python <3.12
                # Treat this path as a literal path
                file_or_dir_paths: tuple[Path, ...] = (path,)
            else:
                base, pattern = split_glob_path(path)
                file_or_dir_paths = get_matching_paths(base, pattern, "file" if is_file else "directory")
                if not file_or_dir_paths:
                    raise DataNotFound(f"Glob pattern {str(path)!r} matched no {'files' if is_file else 'directories'}")
        else:
            if not path.exists():
                raise DataNotFound(f"The provided path does not exist: {str(path)!r}")
            file_or_dir_paths = (path,)
    else:
        data_dir_path, file_or_dir_paths = resolve_relative_path(
            data_loader_option.loader_dir_name,
            data_loader_option.loader_root_dir,
            path,
            load_attrs.search_from,
            is_file=is_file,
        )

    return [
        _data_loader_factory(
            p,
            load_attrs,
            load_from=data_dir_path,
            strip_trailing_whitespace=strip_trailing_whitespace,
            default_encoding=default_encoding,
            ignore_recursive=is_glob,
            gidx_counter=gidx_counter or count(),
            file_cache=file_cache,
        )
        for p in file_or_dir_paths
    ]


def requires_loader(
    *data_loaders: DataLoaderType,
) -> Callable[[Callable[Concatenate[T, P], R]], Callable[Concatenate[T, P], R]]:
    """Limit the function usage to the explicitly specified loaders so that it won't be accidentally used for
    unintended flows
    """

    def decorator(f: Callable[Concatenate[T, P], R]) -> Callable[Concatenate[T, P], R]:
        @wraps(f)
        def wrapper(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
            if self.loader.type not in data_loaders:
                raise NotImplementedError(f"{f.__name__}() is not supported for @{self.loader.type} loader")
            return f(self, *args, **kwargs)

        return wrapper

    return decorator


class Loader(ABC):
    def __init__(
        self,
        path: Path,
        load_attrs: DataLoaderLoadAttrs,
        /,
        *,
        load_from: Path | None = None,
        strip_trailing_whitespace: bool = False,
        default_encoding: str | None = None,
        gidx_counter: count[int] | None = None,
        file_cache: SessionFileCache | None = None,
    ):
        assert path.is_absolute()
        if path.is_symlink():
            check_circular_symlink(path)
        if isinstance(load_attrs.path, Path) and not load_attrs.path.is_absolute() and not load_from:
            raise ValueError("load_from is required when the user specified path is a relative path")

        self.path = path
        self.load_attrs = load_attrs
        self.load_from = load_from
        self.strip_trailing_whitespace = strip_trailing_whitespace
        self.default_encoding = default_encoding or DEFAULT_ENCODING
        self._gidx_counter = gidx_counter or count()
        self._file_cache = file_cache

    @abstractmethod
    def load(self) -> LoadedData | LazyLoadedData | Iterable[LoadedData | LazyLoadedPartData]:
        raise NotImplementedError

    @abstractmethod
    def clear_cache(self) -> None:
        raise NotImplementedError

    @property
    def loader(self) -> DataLoader:
        return self.load_attrs.loader

    def register_cleanup(self, module: ModuleType) -> None:
        """Track a loader on the module-scoped cache.

        :param module: The module object the cache is attached to
        """
        cache: set[Loader] | None = getattr(module, PYTEST_DATA_LOADER_MODULE_CACHE, None)
        if cache is None:
            cache = set()
            setattr(module, PYTEST_DATA_LOADER_MODULE_CACHE, cache)
        cache.add(self)


class FileLoader(Loader):
    """File loader for loading single file"""

    STREAMABLE_FILE_TYPES: ClassVar[tuple[str, ...]] = (".txt", ".log", ".csv", ".tsv")

    def __init__(self, *args: Any, gidx: int | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if not self.path.is_file():
            raise ValueError(f"path must be a file path: {self.path}")

        self._gidx = gidx
        self.read_options = self._get_read_options()
        self.file_reader = self._get_file_reader()
        self._effective_read_mode: str | None = None
        self._effective_encoding = self.read_options.get("encoding") or self.default_encoding
        self._is_multibyte = len("A".encode(self._effective_encoding)) > 1
        # read_mode may still be "auto" here; "auto" != "rb" is intentionally True so that text
        # files (which default to auto-detection) are eligible for streaming. Binary files explicitly set mode="rb"
        # are excluded. _get_file_obj uses text options for the pooled handle so the byte positions from
        # _scan_text_file remain valid regardless of what _resolve_read_mode() later detects.
        self._is_streamable = not is_compressed_path(self.path) and all(
            [
                self.file_reader is None,
                get_effective_suffix(self.path) in FileLoader.STREAMABLE_FILE_TYPES,
                self.read_mode != "rb",
                self.load_attrs.onload_func is None,
                self.load_attrs.parametrizer_func is None,
                not self._is_multibyte,
            ]
        )

        # caches
        self._loaded_data: LoadedData | list[LoadedData] | None = None
        self._file_handles: list[IO[Any]] = []
        weakref.finalize(self, _close_files, self._file_handles)

    @cached_property
    def stat(self) -> os.stat_result:
        return self.path.stat()

    @property
    def read_mode(self) -> str:
        if self._effective_read_mode:
            return self._effective_read_mode

        if mode := self.read_options.get("mode"):
            self._effective_read_mode = mode
        elif any(x in self.read_options for x in ("encoding", "newline")):
            self._effective_read_mode = "r"
        else:
            # This will be identified on the first file read
            return "auto"
        return self._effective_read_mode

    @read_mode.setter
    def read_mode(self, mode: str) -> None:
        self._effective_read_mode = mode

    @property
    def is_streamable(self) -> bool:
        """Whether the file content can be read line by line as stream without loading the entire file"""
        return self._is_streamable

    @cached_property
    @requires_loader(DataLoaderType.PARAMETRIZE)
    def parametrizer_func(self) -> Callable[..., Iterable[Any]]:
        """Returns a normalized parametrizer function that also validates the func result"""
        f = self.load_attrs.parametrizer_func or normalize_loader_func(
            self.loader, self._parametrizer_func, DataLoaderFunctionType.PARAMETRIZER_FUNC
        )

        @wraps(f)
        def _parametrizer_func(*args: Any, **kwargs: Any) -> Iterable[Any]:
            parametrized_data: Any = f(*args, **kwargs)
            if not isinstance(parametrized_data, Iterable) or isinstance(parametrized_data, str | bytes):
                t = parametrized_data if isinstance(parametrized_data, type) else type(parametrized_data)
                raise ValueError(f"Parametrized data must be an iterable container, not {t.__name__}")
            return parametrized_data

        return _parametrizer_func

    def load(self) -> LoadedData | LazyLoadedData | Iterable[LoadedData | LazyLoadedPartData]:
        """Load file data"""
        if self.load_attrs.lazy_loading:
            return self._load_lazily()
        else:
            return self._load_now()

    def clear_cache(self) -> None:
        """Clear caches and any per-instance file handles held by this loader.

        Per-instance handles are always closed here. Session-scoped pooled handles survive until pytest_unconfigure
        clears the session cache.
        """
        _close_files(self._file_handles)
        self._loaded_data = None

    @requires_loader(DataLoaderType.PARAMETRIZE)
    def _parametrizer_func(self, data: Any) -> Iterable[Any]:
        """Default parametrizer function to apply to loaded data when parametrization is needed

        :param data: Loaded data
        """
        if isinstance(data, bytes):
            raise ValueError(f"@{self.loader.__name__} loader requires a custom parametrizer function for binary data")

        if isinstance(data, str):
            stream = StringIO(data)
            return (line.rstrip("\r\n") for line in stream)
        elif isinstance(data, Mapping):
            return iter(data.items())
        elif isinstance(data, Iterator):
            return data
        elif isinstance(data, Iterable):
            return iter(data)
        else:
            try:
                # the data can be still iterable via __getitem__
                return iter(data)
            except TypeError:
                return iter([data])

    def _onload_func(self, data: Any) -> Any:
        """Plugin-managed onload function that will always be applied to the original data that has been loaded.

        :param data: Loaded data or file reader
        """
        if isinstance(data, str) and self.strip_trailing_whitespace:
            data = data.rstrip()
        # TODO: Add more if needed
        return data

    def _load_now(self, skip_processor: bool = False, cache: bool = False) -> LoadedData | list[LoadedData]:
        """Load the entire file data now, then finalize the loaded data after applying all loader functions requested

        :param skip_processor: Whether to skip processing of loaded data. Use this option when you need to apply
                               processor using pre-calculated known param indices (to avoid consuming the idx counter)
                               outside this function
        :param cache: Whether to cache the loaded data for reusing (for lazy loading)
        """
        if not self.load_attrs.lazy_loading and cache:
            raise ValueError("cache option is for lazy loading only")

        if cache and self._loaded_data is not None:
            return self._loaded_data

        data: Any
        if self.file_reader:
            # The file obj needs to remain opened during a test so that a test can access to the loaded data.
            # This will be automatically closed later by the plugin's cleanup fixture.
            f = self._get_file_obj()
            data = self.file_reader(f)
        else:
            data = self._read_file()
        data = self._onload_func(data)

        # Adjust the shape of data based on loader functions
        if self.load_attrs.onload_func:
            data = self.load_attrs.onload_func(self.path, data)

        loaded_data: LoadedData | list[LoadedData]
        if self.loader.should_split_data:
            loaded_data = []
            parts = self.parametrizer_func(self.path, data)
            if self.load_attrs.filter_func:
                parts = (x for x in parts if self.load_attrs.filter_func(self.path, x))
            for part in parts:
                data = part
                if skip_processor:
                    gidx = None
                else:
                    gidx = next(self._gidx_counter)
                    if self.load_attrs.process_func:
                        data = self.load_attrs.process_func(gidx, self.path, part)
                loaded_data.append(LoadedData(file_path=self.path, loaded_from=self.load_from, data=data, gidx=gidx))
        else:
            gidx = self._gidx
            if not skip_processor and self.load_attrs.process_func:
                if gidx is None:
                    gidx = next(self._gidx_counter)
                data = self.load_attrs.process_func(gidx, self.path, data)
            loaded_data = LoadedData(file_path=self.path, loaded_from=self.load_from, data=data, gidx=gidx)

        if cache:
            self._loaded_data = loaded_data

        return loaded_data

    @requires_loader(DataLoaderType.PARAMETRIZE)
    def _load_part_data_now(
        self, *, pos: int, gidx: int, file_loader_func: Callable[..., list[LoadedData]] | None = None
    ) -> LoadedData:
        """Load part data for the specified position now

        :param pos: Position of the part data
        :param gidx: The global index of this part data
        :param file_loader_func: Function to load file data
        """
        if not self.is_streamable and file_loader_func is None:
            raise ValueError("file_loader_func is required for this type of file")

        if file_loader_func:
            loaded_data = file_loader_func()[pos]
            if self.load_attrs.process_func:
                return LoadedData(
                    file_path=self.path,
                    loaded_from=self.load_from,
                    data=self.load_attrs.process_func(gidx, loaded_data.file_path, loaded_data.data),
                    gidx=gidx,
                )
            else:
                return loaded_data
        else:
            f = self._get_file_obj()
            f.seek(pos)
            part_data = f.readline().rstrip("\r\n")
            if self.load_attrs.process_func:
                part_data = self.load_attrs.process_func(gidx, self.path, part_data)
            return LoadedData(file_path=self.path, loaded_from=self.load_from, data=part_data, gidx=gidx)

    def _load_lazily(self) -> LazyLoadedData | Iterable[LazyLoadedPartData]:
        """Lazily load data. The actual data will be resolved when needed in a test"""
        if self.loader.should_split_data:
            # @parametrize() loader handles lazy loading in two different modes depending on the file type and the
            # specified load options. If certain conditions are met, we can split the file content without actually
            # loading the entire file at all. Otherwise, we fall back to the other mode
            if self.is_streamable:
                # Each part data can be inspected without loading the entire file during the collection phase
                scan_results = self._scan_text_file()
                return [
                    LazyLoadedPartData(
                        file_path=self.path,
                        loaded_from=self.load_from,
                        resolver=partial(self._load_part_data_now, pos=pos, gidx=gidx),
                        idx=i,
                        pos=pos,
                        meta=dict(marks=marks, id=param_id),
                        gidx=gidx,
                    )
                    for i, (gidx, pos, marks, param_id) in enumerate(scan_results)
                ]
            else:
                # The entire file content needs to be loaded once during the collection phase to be able to determine
                # the number of parametrized tests by splitting the content. Once it is done, we will not keep the
                # data in memory.
                # NOTE: The actual data loaded with the file loader called during a test setup will be cached and
                #       reused among tests for the same test function
                skip_processor = True
                loaded_data = self._load_now(skip_processor=skip_processor)
                assert isinstance(loaded_data, list)
                file_loader_func = partial(self._load_now, skip_processor=skip_processor, cache=True)
                lazy_parts = []
                for i, data in enumerate(loaded_data):
                    gidx = next(self._gidx_counter)
                    resolver = partial(
                        self._load_part_data_now,
                        pos=i,
                        gidx=gidx,
                        file_loader_func=file_loader_func,  # type: ignore
                    )
                    lazy_parts.append(
                        LazyLoadedPartData(
                            file_path=self.path,
                            loaded_from=self.load_from,
                            resolver=resolver,
                            idx=i,
                            meta=dict(
                                marks=self.load_attrs.marker_func(gidx, self.path, data.data)
                                if self.load_attrs.marker_func
                                else None,
                                id=self.load_attrs.id_func(gidx, self.path, data.data)
                                if self.load_attrs.id_func
                                else None,
                            ),
                            gidx=gidx,
                        )
                    )
                return lazy_parts
        else:
            return LazyLoadedData(
                file_path=self.path,
                loaded_from=self.load_from,
                resolver=partial(self._load_now, cache=True),
                gidx=self._gidx,
            )

    def _get_file_obj(self) -> IO[Any]:
        """Return an open file handle for this loader.

        When a session cache is available and no file_reader is in use, the handle is drawn from the session
        pool (bounded, shared across instances for the same path and read options).  When a file_reader is present
        the handle must remain open for the duration of the test (the reader may hold it lazily), so a per-instance
        handle is used instead — the pool would close it on eviction.

        Pool callers are responsible for seeking to their desired position before reading.
        """
        if self._file_cache is not None and self._file_cache.pooling_enabled and self.file_reader is None:
            # Use the same options as _scan_text_file (text mode, no explicit mode resolution) so
            # that byte positions recorded during scanning remain valid for this handle.
            read_options = self._effective_read_options()
            return self._file_cache.get_handle(
                self._build_session_cache_key(read_options),
                on_miss=lambda: compression_aware_open(self.path, **read_options),
            )
        elif self._file_handles and not self._file_handles[0].closed:
            f = self._file_handles[0]
            f.seek(0)
            return f
        else:
            f = compression_aware_open(self.path, **self._effective_read_options())
            self._file_handles[:] = [f]
            return f

    @requires_loader(DataLoaderType.PARAMETRIZE)
    def _scan_text_file(self) -> Generator[tuple[int, int, Any, Any]]:
        """Scan file and returns metadata for each part data that should be loaded.

        Each yielded tuple is (gidx, pos, marks, param_id) where gidx is the zero-based global post-filter
        position passed to the loader callable options.

        NOTE: The following loader functions will be applied to each part data as part of the scan
        - filter_func
        - marker_func
        - id_func
        """
        assert self.loader.should_split_data and self.is_streamable
        results: list[tuple[int, int, Any, Any]] = []
        buffer: list[tuple[int, Any]] = []

        def commit(pos: int, part: Any) -> None:
            """Commit a part to results, drawing gidx and evaluating marker/id now."""
            gidx = next(self._gidx_counter)
            param_marks = self.load_attrs.marker_func(gidx, self.path, part) if self.load_attrs.marker_func else None
            param_id = self.load_attrs.id_func(gidx, self.path, part) if self.load_attrs.id_func else None
            results.append((gidx, pos, param_marks, param_id))

        def inspect_part_data(pos: int, part: Any) -> None:
            if not self.load_attrs.filter_func or self.load_attrs.filter_func(self.path, part):
                if isinstance(part, str) and self.strip_trailing_whitespace:
                    if part.rstrip() == "":
                        # whitespace-only line; defer idx draw until we know it's not trailing
                        buffer.append((pos, part))
                    else:
                        # flush previous whitespace lines as they weren't trailing
                        if buffer:
                            for buf_pos, buf_part in buffer:
                                commit(buf_pos, buf_part)
                            buffer.clear()
                        commit(pos, part)
                else:
                    commit(pos, part)

        with compression_aware_open(self.path, **self._effective_read_options()) as f:
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    # EOF
                    break

                line = line.rstrip("\r\n")
                inspect_part_data(pos, line)

        yield from results

    def _read_file(self) -> str | bytes:
        """Read file data, served from the session content cache when available."""
        assert self.path.is_absolute()
        read_options = self._effective_read_options(mode=self._resolve_read_mode())

        def read_from_disk() -> str | bytes:
            with compression_aware_open(self.path, **read_options) as f:
                return f.read()

        if self._file_cache is not None:
            return self._file_cache.get_content(self._build_session_cache_key(read_options), on_miss=read_from_disk)
        return read_from_disk()

    def _resolve_read_mode(self) -> str:
        """Resolve and cache the effective read mode, running auto-detection when needed."""
        if self.read_mode == "auto":
            self.read_mode = self._detect_read_mode()
        return self.read_mode

    def _detect_read_mode(self) -> Literal["r", "rb"]:
        """Return the detected read mode ("r" or "rb") for this file.

        When a session cache is available the result is memoized so the 4 KiB binary
        probe runs at most once per (file, encoding) combination per session.
        """

        def probe() -> Literal["r", "rb"]:
            is_binary = False
            with compression_aware_open(self.path, mode="rb") as f:
                chunk = f.read(4096)
            if chunk:
                # Null bytes are a fast-path (utf-8 and single-byte codecs never contain
                # them in valid text), but multibyte encodings like utf-16 legitimately
                # interleave nulls, so skip the short-circuit for those.
                if not self._is_multibyte and b"\x00" in chunk:
                    is_binary = True
                elif not can_decode(chunk, DEFAULT_ENCODING):
                    # utf-8 probe failed; fall back to the configured encoding if different.
                    # Incremental decoding tolerates a partial multibyte char at the chunk boundary.
                    if self._effective_encoding == DEFAULT_ENCODING or not can_decode(chunk, self._effective_encoding):
                        is_binary = True
            return "rb" if is_binary else "r"

        if self._file_cache is not None:
            cache_key: ReadModeKey = (
                str(self.path),
                self.stat.st_mtime_ns,
                self.stat.st_size,
                self._effective_encoding,
            )
            return self._file_cache.get_read_mode(cache_key, on_miss=probe)
        return probe()

    def _effective_read_options(self, *, mode: str | None = None) -> dict[str, Any]:
        """Return read_options merged with the configured default encoding when applicable.

        The default encoding is injected only when the resulting open mode is text and no explicit
        'encoding' has been provided in read_options. self.read_options (a HashableDict used as a
        cache key) is never mutated.

        :param mode: Optional explicit mode to merge into the returned options.
        """
        options: dict[str, Any] = dict(self.read_options)
        if mode is not None:
            options["mode"] = mode
        effective_mode = options.get("mode") or "r"
        if "b" not in effective_mode and "encoding" not in options:
            options["encoding"] = self._effective_encoding
        return options

    def _get_read_options(self) -> HashableDict:
        if self.load_attrs.read_options_func:
            assert isinstance(self._gidx, int)
            read_options = self.load_attrs.read_options_func(self._gidx, self.path, None)
            validate_read_options(read_options)
            return HashableDict(read_options)
        else:
            return self.load_attrs.read_options

    def _get_file_reader(self) -> Callable[..., Any] | None:
        if self.load_attrs.reader_func:
            assert isinstance(self._gidx, int)
            file_reader = self.load_attrs.reader_func(self._gidx, self.path, None)
            validate_reader(file_reader)
        else:
            file_reader = self.load_attrs.reader
        if not file_reader:
            if registered_reader := FileReader.get_registered_reader(
                self.load_attrs.search_from, get_effective_suffix(self.path)
            ):
                file_reader = registered_reader.reader
                if not self.read_options:
                    self.read_options = registered_reader.read_options
        return file_reader

    def _build_session_cache_key(self, read_options: dict[str, Any]) -> CacheKey:
        """Build the session content/handle cache key for this file and read options."""
        return (str(self.path), self.stat.st_mtime_ns, self.stat.st_size, HashableDict(read_options))


class DirectoryLoader(Loader):
    """Data loader for loading files in a directory"""

    def __init__(self, *args: Any, ignore_recursive: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if not self.path.is_dir():
            raise ValueError(f"path must be a directory path: {self.path}")
        if self.loader.is_file_loader:
            raise NotImplementedError(f"Unsupported loader for {DirectoryLoader.__name__}: {self.loader}")
        self._ignore_recursive = ignore_recursive
        self._file_loaders: list[FileLoader] = []
        weakref.finalize(self, _clear_dir_loader_caches, self._file_loaders)

    def clear_cache(self) -> None:
        """Clear file loader cache associated with this directory loader"""
        _clear_dir_loader_caches(self._file_loaders)

    def load(self) -> Iterable[LoadedData | LazyLoadedData]:  # type: ignore[override]
        """Load multiple files from a directory"""

        def load_file(file_path: Path) -> None:
            if not file_path.name.startswith("."):
                if not self.load_attrs.filter_func or self.load_attrs.filter_func(file_path, None):
                    gidx = next(self._gidx_counter)
                    file_loader = FileLoader(
                        file_path,
                        self.load_attrs,
                        load_from=self.load_from,
                        strip_trailing_whitespace=self.strip_trailing_whitespace,
                        default_encoding=self.default_encoding,
                        gidx=gidx,
                        file_cache=self._file_cache,
                    )
                    loaded_data = file_loader.load()
                    assert isinstance(loaded_data, LoadedData | LazyLoadedData), type(loaded_data)
                    self._file_loaders.append(file_loader)
                    loaded_files.append(loaded_data)

        def walk(dir_path: Path, *, is_base: bool = False) -> None:
            if is_base or not dir_path.name.startswith("."):
                check_and_track_dir(dir_path, visited_dirs)
                for p in sorted(dir_path.iterdir()):
                    if p.is_dir():
                        walk(p)
                    else:
                        load_file(p)

        visited_dirs: set[tuple[int, int]] = set()
        loaded_files: list[LoadedData | LazyLoadedData] = []
        if self.load_attrs.recursive and not self._ignore_recursive:
            walk(self.path, is_base=True)
        else:
            for p in sorted(self.path.iterdir()):
                if p.is_file():
                    load_file(p)

        return loaded_files


def _data_loader_factory(
    abs_data_path: Path,
    load_attrs: DataLoaderLoadAttrs,
    /,
    *,
    load_from: Path | None = None,
    strip_trailing_whitespace: bool,
    default_encoding: str | None = None,
    ignore_recursive: bool = False,
    gidx_counter: count[int],
    file_cache: SessionFileCache | None = None,
) -> FileLoader | DirectoryLoader:
    """Data loader factory that creates either FileLoader or DirectoryLoader depending on the specified path

    :param abs_data_path: File or directory's absolute path
    :param load_attrs: Data loader attributes
    :param load_from: Data directory to load from
    :param strip_trailing_whitespace: Whether to strip trailing whitespace from loaded data
    :param default_encoding: Default text encoding when no encoding is set in read_options
    :param ignore_recursive: When True, DirectoryLoader will ignore the recursive flag
    :param gidx_counter: Global index counter that produces continuous post-filter idx values across all loaders
    :param file_cache: Session-scoped file cache; ``None`` disables session caching
    """
    if not abs_data_path.is_absolute():
        raise ValueError("abs_data_path must be an absolute path")

    if abs_data_path.is_file():
        return FileLoader(
            abs_data_path,
            load_attrs,
            load_from=load_from,
            strip_trailing_whitespace=strip_trailing_whitespace,
            default_encoding=default_encoding,
            gidx_counter=gidx_counter,
            file_cache=file_cache,
        )
    else:
        return DirectoryLoader(
            abs_data_path,
            load_attrs,
            load_from=load_from,
            strip_trailing_whitespace=strip_trailing_whitespace,
            default_encoding=default_encoding,
            ignore_recursive=ignore_recursive,
            gidx_counter=gidx_counter,
            file_cache=file_cache,
        )


def _close_files(file_handlers: list[IO[Any]]) -> None:
    """Close a FileLoader's open handle.

    :param file_handlers: Open file handles
    """
    for f in file_handlers:
        try:
            f.close()
        except Exception as e:
            logger.exception(e)
    file_handlers.clear()


def _clear_dir_loader_caches(file_loaders: list[FileLoader]) -> None:
    """Release all caches held by a DirectoryLoader instance

    :param file_loaders: FileLoader instances associated with a DirectoryLoader instance
    """
    for file_loader in file_loaders:
        file_loader.clear_cache()
    file_loaders.clear()
