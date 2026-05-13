from __future__ import annotations

import glob
import logging
import os
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from functools import cached_property, lru_cache, partial, wraps
from io import StringIO
from itertools import count
from pathlib import Path
from types import ModuleType
from typing import IO, Any, ClassVar, Concatenate, ParamSpec, TypeVar

from pytest_data_loader.constants import PYTEST_DATA_LOADER_MODULE_CACHE
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.loaders.reader import FileReader
from pytest_data_loader.paths import (
    check_and_track_dir,
    check_circular_symlink,
    get_matching_paths,
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
from pytest_data_loader.utils import normalize_loader_func
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
    gidx_counter: count[int] | None = None,
) -> list[FileLoader | DirectoryLoader]:
    """Resolve a single path entry (which may be a glob pattern or a concrete path) to file or directory loaders.
    Returns one loader per matched entry (possibly many when *path* is a glob pattern).

    :param path: A single path entry from the data loader's path argument. This can be a glob pattern
    :param load_attrs: Loader attributes for the current data loader
    :param data_loader_option: Data loader options
    :param gidx_counter: Global index counter that produces continuous post-filter idx values across all loaders
                         created for a single decorator invocation
    """
    strip_trailing_whitespace = bool(data_loader_option.strip_trailing_whitespace)
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
            ignore_recursive=is_glob,
            gidx_counter=gidx_counter or count(),
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
        gidx_counter: count[int] | None = None,
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
        self._gidx_counter = gidx_counter or count()

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
        self.file_reader = self.load_attrs.reader
        self.read_options = self.load_attrs.read_options
        if not self.file_reader:
            if registered_reader := FileReader.get_registered_reader(self.load_attrs.search_from, self.path.suffix):
                self.file_reader = registered_reader.reader
                if not self.read_options:
                    self.read_options = registered_reader.read_options
        assert isinstance(self.read_options, HashableDict)
        self._effective_read_mode: str | None = None
        self._is_streamable = self.file_reader is not None or all(
            # non-structured text data can be read line by line
            [
                self.path.suffix in FileLoader.STREAMABLE_FILE_TYPES,
                self.read_mode != "rb",
                self.load_attrs.onload_func is None,
                self.load_attrs.parametrizer_func is None,
            ]
        )

        # Caches used by data loaders.
        # NOTE: In Pytest, these cache data will be cleared as a module teardown managed by the plugin
        self._cached_file_objects: dict[tuple[Path, HashableDict], IO[Any]] = {}
        self._cached_functions: set[Callable[..., Any]] = set()
        self._cached_reader_and_split: dict[Callable[..., Any], list[Any]] = {}
        weakref.finalize(
            self,
            _clear_file_loader_caches,
            self._cached_file_objects,
            self._cached_functions,
            self._cached_reader_and_split,
        )

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
        """Clear cache associated with this file loader"""
        _clear_file_loader_caches(self._cached_file_objects, self._cached_functions, self._cached_reader_and_split)

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

    def _load_now(self, skip_processor: bool = False) -> LoadedData | Iterable[LoadedData]:
        """Load the entire file data now, then finalize the loaded data after applying all loader functions requested

        :param skip_processor: Whether to skip processing of loaded data. Use this option when you need to apply
                               processor using pre-calculated known param indices (to avoid consuming the idx counter)
                               outside this function

        NOTE: When resolving lazily loaded part data, this function result will be dynamically cached to share it among
              all part data
        """
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

        if self.loader.should_split_data:
            parts = self.parametrizer_func(self.path, data)
            if self.load_attrs.filter_func:
                parts = (x for x in parts if self.load_attrs.filter_func(self.path, x))
            loaded_data: list[LoadedData] = []
            for part in parts:
                data = part
                if skip_processor:
                    gidx = None
                else:
                    gidx = next(self._gidx_counter)
                    if self.load_attrs.process_func:
                        data = self.load_attrs.process_func(gidx, self.path, part)
                loaded_data.append(LoadedData(file_path=self.path, loaded_from=self.load_from, data=data, gidx=gidx))
            return loaded_data
        else:
            gidx = self._gidx
            if not skip_processor and self.load_attrs.process_func:
                if gidx is None:
                    gidx = next(self._gidx_counter)
                data = self.load_attrs.process_func(gidx, self.path, data)
            return LoadedData(file_path=self.path, loaded_from=self.load_from, data=data, gidx=gidx)

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
            if self.file_reader:
                data = self._read_reader_and_split(self.file_reader, f)
                part_data = data[pos]
            else:
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
                loaded_data = self._load_now(skip_processor=True)
                assert isinstance(loaded_data, list)
                file_loader_func = lru_cache(maxsize=1)(partial(self._load_now, skip_processor=True))
                self._cached_functions.add(file_loader_func)
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
            # Caches the loaded data for reusing in case other parametrized loader is stacked
            file_loader_func = lru_cache(maxsize=1)(self._load_now)
            self._cached_functions.add(file_loader_func)
            return LazyLoadedData(
                file_path=self.path,
                loaded_from=self.load_from,
                resolver=file_loader_func,
                gidx=self._gidx,
            )

    def _get_file_obj(self) -> IO[Any]:
        """Get file object from cache or open a new one and cache it"""
        f = self._cached_file_objects.get((self.path, self.read_options))
        if not f or f.closed:
            f = open(self.path, **self.read_options)
            self._cached_file_objects[(self.path, self.read_options)] = f
        f.seek(0)
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

        with open(self.path, **self.read_options) as f:
            if self.file_reader:
                # NOTE: Do NOT use _read_reader_and_split here to get the split data. Closing the file will invalidate
                #       the cached part data generated by the file reader and cause issues when loading part data later.
                reader = self.file_reader(f)
                if self.load_attrs.onload_func:
                    reader = self.load_attrs.onload_func(self.path, reader)
                for i, part in enumerate(self.parametrizer_func(self.path, reader)):
                    inspect_part_data(i, part)
            else:
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
        """Read file data"""
        assert self.path.is_absolute()
        if self.read_mode == "auto":
            # Detect read mode based on sampled data
            is_binary = False
            with open(self.path, "rb") as f:
                chunk = f.read(4096)

            if chunk:
                if b"\x00" in chunk:
                    is_binary = True
                else:
                    try:
                        chunk.decode("utf-8")
                    except UnicodeDecodeError:
                        is_binary = True

            read_mode = "rb" if is_binary else "r"
            self.read_mode = read_mode

        read_options = dict(self.read_options) | {"mode": self.read_mode}
        if self.read_mode == "r" and "encoding" not in read_options:
            read_options["encoding"] = "utf-8"

        with open(self.path, **read_options) as f:
            return f.read()

    @requires_loader(DataLoaderType.PARAMETRIZE)
    def _read_reader_and_split(self, file_reader: Callable[..., Iterable[Any] | object], f: IO[Any]) -> list[Any]:
        """Read full data from the file reader and split into parts, caching the result per reader.

        :param file_reader: A file reader to read data from
        :param f: File object to read from
        """
        if file_reader not in self._cached_reader_and_split:
            f.seek(0)
            reader = file_reader(f)
            if self.load_attrs.onload_func:
                reader = self.load_attrs.onload_func(self.path, reader)
            self._cached_reader_and_split[file_reader] = list(self.parametrizer_func(self.path, reader))
        return self._cached_reader_and_split[file_reader]


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
                        gidx=gidx,
                    )
                    file_reader = read_options = None
                    if self.load_attrs.read_options_func:
                        read_options = self.load_attrs.read_options_func(gidx, file_path, None)
                    if self.load_attrs.reader_func:
                        file_reader = self.load_attrs.reader_func(gidx, file_path, None)
                    if file_reader:
                        validate_reader(file_reader)
                        file_loader.file_reader = file_reader
                    if read_options:
                        validate_read_options(read_options)
                        file_loader.read_options = HashableDict(read_options)
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
    ignore_recursive: bool = False,
    gidx_counter: count[int],
) -> FileLoader | DirectoryLoader:
    """Data loader factory that creates either FileLoader or DirectoryLoader depending on the specified path

    :param abs_data_path: File or directory's absolute path
    :param load_attrs: Data loader attributes
    :param load_from: Data directory to load from
    :param strip_trailing_whitespace: Whether to strip trailing whitespace from loaded data
    :param ignore_recursive: When True, DirectoryLoader will ignore the recursive flag
    :param gidx_counter: Global index counter that produces continuous post-filter idx values across all loaders
    """
    if not abs_data_path.is_absolute():
        raise ValueError("abs_data_path must be an absolute path")

    if abs_data_path.is_file():
        return FileLoader(
            abs_data_path,
            load_attrs,
            load_from=load_from,
            strip_trailing_whitespace=strip_trailing_whitespace,
            gidx_counter=gidx_counter,
        )
    else:
        return DirectoryLoader(
            abs_data_path,
            load_attrs,
            load_from=load_from,
            strip_trailing_whitespace=strip_trailing_whitespace,
            ignore_recursive=ignore_recursive,
            gidx_counter=gidx_counter,
        )


def _clear_file_loader_caches(
    cached_file_objects: dict[tuple[Path, HashableDict], IO[Any]],
    cached_functions: set[Callable[..., Any]],
    cached_reader_split: dict[Callable[..., Any], list[Any]],
) -> None:
    """Release all caches held by a FileLoader instance

    :param cached_file_objects: Open file handles keyed by (path, read_options)
    :param cached_functions: lru_cache-wrapped functions
    :param cached_reader_split: Per-reader split results
    """
    if cached_file_objects:
        for f in cached_file_objects.values():
            try:
                f.close()
            except Exception as e:
                logger.exception(e)
        cached_file_objects.clear()

    if cached_functions:
        for loader_func in cached_functions:
            try:
                loader_func.cache_clear()  # type: ignore[attr-defined]
            except Exception as e:
                logger.exception(e)
        cached_functions.clear()

    cached_reader_split.clear()


def _clear_dir_loader_caches(file_loaders: list[FileLoader]) -> None:
    """Release all caches held by a DirectoryLoader instance

    :param file_loaders: FileLoader instances associated with a DirectoryLoader instance
    """
    for file_loader in file_loaders:
        file_loader.clear_cache()
    file_loaders.clear()
