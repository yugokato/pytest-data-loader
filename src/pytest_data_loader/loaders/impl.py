from __future__ import annotations

import logging
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from functools import cached_property, lru_cache, partial, wraps
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import Any, ClassVar, ParamSpec, TypeVar

from pytest_data_loader import parametrize
from pytest_data_loader.loaders.reader import FileReader
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    HashableDict,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
)
from pytest_data_loader.utils import validate_loader_func_args_and_normalize

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


def data_loader_factory(
    abs_data_path: Path,
    load_attrs: DataLoaderLoadAttrs,
    /,
    *,
    load_from: Path | None = None,
    strip_trailing_whitespace: bool,
) -> FileDataLoader | DirectoryDataLoader:
    """Data loader factory that creates either FileDataLoader or DirectoryDataLoader depending on the specified path

    :param abs_data_path: File or directory's absolute path
    :param load_attrs: Data loader attributes
    :param load_from: Data directory to load from
    :param strip_trailing_whitespace: Whether to strip trailing whitespace from loaded data
    """
    if not abs_data_path.is_absolute():
        raise ValueError("abs_data_path must be an absolute path")

    if abs_data_path.is_file():
        return FileDataLoader(
            abs_data_path, load_attrs, load_from=load_from, strip_trailing_whitespace=strip_trailing_whitespace
        )
    else:
        return DirectoryDataLoader(
            abs_data_path, load_attrs, load_from=load_from, strip_trailing_whitespace=strip_trailing_whitespace
        )


def requires_loader(*loaders: Callable[..., Any]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Limit the function usage to the explicitly specified loaders so that it won't be accidentally used for
    unintended flows
    """

    def decorator(f: Callable[P, R]) -> Callable[P, R]:
        @wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            assert args and isinstance(args[0], FileDataLoader)
            self: FileDataLoader = args[0]
            if self.loader not in loaders:
                raise NotImplementedError(f"{f.__name__}() is not supported for @{self.loader.__name__} loader")
            return f(*args, **kwargs)

        return wrapper

    return decorator


@lru_cache
def resolve_relative_path(
    data_loader_dir_name: str,
    data_loader_root_dir: Path,
    relative_path_to_search: Path,
    search_from: Path,
    /,
    *,
    is_file: bool,
) -> tuple[Path, Path]:
    """Locate the given relative file or directory path in the nearest data directory by searching upwards from the
    current location

    :param data_loader_dir_name: The data directory name
    :param data_loader_root_dir: A root directory the path lookup should stop at
    :param relative_path_to_search: A file or directory path relative from a data loader directory
    :param search_from: A file or directory path to start searching from
    :param is_file: Whether the relative path is file or directory
    """
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
    for dir_to_search in (search_from, *(search_from.parents)):
        data_dir = dir_to_search / data_loader_dir_name
        if data_dir.exists():
            data_dirs.append(data_dir)
            file_or_dir_path = data_dir / relative_path_to_search
            if file_or_dir_path.exists():
                # Ignore if a directory with the same name as the required file (or vice versa) is found
                if (file_or_dir_path.is_file() and is_file) or (file_or_dir_path.is_dir() and not is_file):
                    return data_dir, file_or_dir_path.resolve()

        if dir_to_search == data_loader_root_dir:
            break

    if data_dirs:
        listed_data_dirs = "\n".join(f"  - {x}" for x in data_dirs)
        err = (
            f"Unable to locate the specified {'file' if is_file else 'directory'} '{relative_path_to_search}' under "
            f"any of the following data directories:\n"
            f"{listed_data_dirs}"
        )
    else:
        err = f"Unable to find any data directory '{data_loader_dir_name}'"
    raise FileNotFoundError(err)


class LoaderABC(ABC):
    def __init__(
        self,
        path: Path,
        load_attrs: DataLoaderLoadAttrs,
        /,
        *,
        load_from: Path | None = None,
        strip_trailing_whitespace: bool = False,
    ):
        assert path.is_absolute()
        if not load_attrs.path.is_absolute() and not load_from:
            raise ValueError("load_from is required when the user specified path is a relative path")
        self.path = path
        self.load_attrs = load_attrs
        self.load_from = load_from
        self.strip_trailing_whitespace = strip_trailing_whitespace

    @abstractmethod
    def load(self) -> LoadedData | LazyLoadedData | Iterable[LoadedData | LazyLoadedPartData]:
        raise NotImplementedError

    @property
    def loader(self) -> DataLoader:
        return self.load_attrs.loader


class FileDataLoader(LoaderABC):
    """File loader for loading single file"""

    STREAMABLE_FILE_TYPES: ClassVar[tuple[str, ...]] = (".txt", ".log", ".csv", ".tsv")

    @wraps(LoaderABC.__init__)  # type: ignore[misc]
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if not self.path.is_file():
            raise ValueError(f"path must be a file path: {self.path}")
        self.file_reader = self.load_attrs.file_reader
        self.read_options = self.load_attrs.read_options
        if not self.file_reader:
            if registered_reader := FileReader.get_registered_reader(self.load_attrs.search_from, self.path.suffix):
                self.file_reader = registered_reader.reader
                if not self.read_options:
                    self.read_options = registered_reader.read_options
        assert isinstance(self.read_options, HashableDict)
        self._is_streamable = self.file_reader is not None or all(
            # non-structured text data can be read line by line
            [
                self.path.suffix in FileDataLoader.STREAMABLE_FILE_TYPES,
                self.read_mode != "rb",
                self.load_attrs.onload_func is None,
                self.load_attrs.parametrizer_func is None,
            ]
        )
        # caches used by the @parametrize loader.
        # NOTE: In Pytest, these cache data will be cleared as a module teardown managed by the plugin
        self._cached_file_objects: dict[tuple[Path, HashableDict], TextIOWrapper] = {}
        self._cached_file_loaders: set[Callable[..., Any]] = set()
        if self.loader == parametrize:
            weakref.finalize(self, self.clear_cache)

    @property
    def read_mode(self) -> str:
        if mode := self.read_options.get("mode"):
            return mode
        elif any(x in self.read_options for x in ("encoding", "newline")):
            return "r"
        else:
            # This will be identified on the first file read
            return "auto"

    @read_mode.setter
    def read_mode(self, mode: str) -> None:
        self.read_options["mode"] = mode

    @property
    def is_streamable(self) -> bool:
        """Whether the file content can be read line by line as stream without loading the entier file"""
        return self._is_streamable

    @cached_property
    @requires_loader(parametrize)
    def parametrizer_func(self) -> Callable[..., Iterable[Any]]:
        """Returns a normalized parametrizer function that also validates the func result"""
        f = self.load_attrs.parametrizer_func or validate_loader_func_args_and_normalize(self._parametrizer_func)

        @wraps(f)
        def _parametrizer_func(*args: Any, **kwargs: Any) -> Iterable[Any]:
            parametrized_data: Any = f(*args, **kwargs)
            if not isinstance(parametrized_data, Iterable) or isinstance(parametrized_data, str | bytes):
                t = parametrized_data if isinstance(parametrized_data, type) else type(parametrized_data)
                raise ValueError(f"Parametrized data must be an iterable container, not {t.__name__!r}")
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
        if self._cached_file_objects:
            for p in self._cached_file_objects:
                try:
                    self._cached_file_objects[p].close()
                except Exception as e:
                    logger.exception(e)
            self._cached_file_objects.clear()

        if self._cached_file_loaders:
            for f in self._cached_file_loaders:
                try:
                    f.cache_clear()  # type: ignore[attr-defined]
                except Exception as e:
                    logger.exception(e)
            self._cached_file_loaders.clear()

        try:
            self._read_reader_and_split.cache_clear()
        except Exception as e:
            logger.exception(e)

    @requires_loader(parametrize)
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
        """Plugin-managed onload function that will allways be applied to the original data that has been loaded.

        :param data: Loaded data or file reader
        """
        if isinstance(data, str) and self.strip_trailing_whitespace:
            data = data.rstrip()
        # TODO: Add more if needed
        return data

    def _load_now(self) -> LoadedData | Iterable[LoadedData]:
        """Load the entire file data now, then finalize the loaded data after applying all loader functions requested

        NOTE: When resolving lazily loaded part data, this function result will be dynamically cached to share it among
              all part data
        """
        if self.file_reader:
            f = self._get_file_obj()
            data = self.file_reader(f)
        else:
            data = self._read_file()
        data = self._onload_func(data)

        # Adjust the shape of data based on loader functions
        if self.load_attrs.onload_func:
            data = self.load_attrs.onload_func(self.path, data)

        if self.loader.should_split_data:
            data = self.parametrizer_func(self.path, data)
            if self.load_attrs.filter_func:
                data = (x for x in data if self.load_attrs.filter_func(self.path, x))
            if self.load_attrs.process_func:
                data = (self.load_attrs.process_func(self.path, x) for x in data)
            return [LoadedData(file_path=self.path, loaded_from=self.load_from, data=x) for x in data]
        else:
            if self.load_attrs.process_func:
                data = self.load_attrs.process_func(self.path, data)
            return LoadedData(file_path=self.path, loaded_from=self.load_from, data=data)

    @requires_loader(parametrize)
    def _load_part_data_now(self, pos: int, /, *, close: bool = True) -> LoadedData:
        """Load part data for the specified position now

        :param pos: Position of the part data
        :param close: Close the file. Otherwise, the file object will be cached for reusing
        """
        if not self.is_streamable:
            raise NotImplementedError("Part data loading is not supported for this type of file")

        f = self._get_file_obj()
        try:
            if self.file_reader:
                data = self._read_reader_and_split(self.file_reader, f)
                part_data = data[pos]
            else:
                f.seek(pos)
                part_data = f.readline().rstrip("\r\n")
            if self.load_attrs.process_func:
                part_data = self.load_attrs.process_func(self.path, part_data)
            return LoadedData(file_path=self.path, loaded_from=self.load_from, data=part_data)
        finally:
            has_cache = (self.path, self.read_options) in self._cached_file_objects
            if close:
                f.close()
                if has_cache:
                    del self._cached_file_objects[(self.path, self.read_options)]
            else:
                if not has_cache:
                    self._cached_file_objects[(self.path, self.read_options)] = f

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
                        file_loader=partial(self._load_part_data_now, pos, close=False),
                        idx=i,
                        pos=pos,
                        meta=dict(marks=marks, id=param_id),
                    )
                    for i, (pos, marks, param_id) in enumerate(scan_results)
                ]
            else:
                # The entire file content needs to be loaded once during the collection phase to be able to determine
                # the number of parametrized tests by splitting the content. Once it is done,
                # we will not keep the data in memory
                # NOTE: The actual data loaded with the file loader called during a test setup will be cached and
                #       reused among tests for the same test function
                loaded_data = self._load_now()
                assert isinstance(loaded_data, list)
                file_loader = lru_cache(maxsize=1)(self._load_now)
                return [
                    LazyLoadedPartData(
                        file_path=self.path,
                        loaded_from=self.load_from,
                        file_loader=file_loader,
                        idx=i,
                        meta=dict(
                            marks=self.load_attrs.marker_func(self.path, data.data)
                            if self.load_attrs.marker_func
                            else None,
                            id=self.load_attrs.id_func(self.path, data.data) if self.load_attrs.id_func else None,
                        ),
                        # Add the file loader to the cache when the part data is resolved
                        post_load_hook=partial(self._cached_file_loaders.add, file_loader),
                    )
                    for i, data in enumerate(loaded_data)
                ]
        else:
            return LazyLoadedData(file_path=self.path, loaded_from=self.load_from, file_loader=self._load_now)

    def _get_file_obj(self) -> TextIOWrapper:
        """Get file object from cache or open a new one"""
        f = self._cached_file_objects.get((self.path, self.read_options))
        is_closed = f and f.closed
        if not f or is_closed:
            f = open(self.path, **self.read_options)
            if is_closed:
                self._cached_file_objects[(self.path, self.read_options)] = f
        f.seek(0)
        return f

    @requires_loader(parametrize)
    def _scan_text_file(self) -> Generator[tuple[int, Any, Any]]:
        """Scan file and returns metadata for each part data that should be loaded.

        NOTE: The following loader functions will be applied to each part data as part of the scan
        - filter_func
        - marker_func
        - id_func
        """
        assert self.loader.should_split_data and self.is_streamable
        results = []
        buffer = []

        def inspect_part_data(pos: int, part: Any) -> None:
            if not self.load_attrs.filter_func or self.load_attrs.filter_func(self.path, part):
                param_id = param_marks = None
                if self.load_attrs.marker_func:
                    param_marks = self.load_attrs.marker_func(self.path, part)
                if self.load_attrs.id_func:
                    param_id = self.load_attrs.id_func(self.path, part)
                if isinstance(part, str) and self.strip_trailing_whitespace:
                    if part.rstrip() == "":
                        # whitespace-only line
                        buffer.append((pos, param_marks, param_id))
                    else:
                        # flush previous whitespace lines as they weren't trailing
                        if buffer:
                            results.extend(buffer)
                            buffer.clear()
                        results.append((pos, param_marks, param_id))
                else:
                    results.append((pos, param_marks, param_id))

        with open(self.path, **self.read_options) as f:
            if self.file_reader:
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
        data: str | bytes
        if self.read_mode == "auto":
            try:
                # Without specifying encoding, this logic fails for binary data on windows
                with open(self.path, encoding="utf-8", **self.read_options) as f:
                    data = f.read()
            except UnicodeDecodeError:
                read_mode = "rb"
                with open(self.path, read_mode, **self.read_options) as f:
                    data = f.read()
                # set the determined read mode
                self.read_mode = read_mode
        else:
            with open(self.path, **self.read_options) as f:
                data = f.read()
        return data

    @lru_cache(maxsize=1)
    @requires_loader(parametrize)
    def _read_reader_and_split(self, file_reader: Callable[..., Iterable[Any] | object], f: TextIOWrapper) -> list[Any]:
        """Read full data from the file reader and split into parts

        :param file_reader: A file reader to read data from
        """
        f.seek(0)
        reader = file_reader(f)
        if self.load_attrs.onload_func:
            reader = self.load_attrs.onload_func(self.path, reader)
        return list(self.parametrizer_func(self.path, reader))


class DirectoryDataLoader(LoaderABC):
    """Data loader for loading files in a directory"""

    @wraps(LoaderABC.__init__)  # type: ignore[misc]
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if not self.path.is_dir():
            raise ValueError(f"path must be a directory path: {self.path}")
        if self.loader.is_file_loader:
            raise NotImplementedError(f"Unsupported loader for {DirectoryDataLoader.__name__}: {self.loader}")

    def load(self) -> Iterable[LoadedData | LazyLoadedData]:  # type: ignore[override]
        """Load multiple files from a directory"""

        def load_files(dir_path: Path) -> None:
            for p in sorted(dir_path.iterdir()):
                if p.is_dir():
                    if self.load_attrs.recursive:
                        load_files(p)
                elif not p.name.startswith("."):
                    file_path = dir_path / p.name
                    if not self.load_attrs.filter_func or self.load_attrs.filter_func(file_path):
                        file_loader = FileDataLoader(
                            file_path,
                            self.load_attrs,
                            load_from=self.load_from,
                            strip_trailing_whitespace=self.strip_trailing_whitespace,
                        )
                        file_reader = read_options = None
                        if self.load_attrs.read_option_func:
                            read_options = self.load_attrs.read_option_func(file_path)
                        if self.load_attrs.file_reader_func:
                            file_reader = self.load_attrs.file_reader_func(file_path)
                        if file_reader or read_options:
                            FileReader.validate(file_reader, read_options)
                            if file_reader:
                                file_loader.file_reader = file_reader
                            if read_options:
                                file_loader.read_options = HashableDict(read_options)
                        loaded_data = file_loader.load()
                        assert isinstance(loaded_data, LoadedData | LazyLoadedData), type(loaded_data)
                        loaded_files.append(loaded_data)

        loaded_files: list[LoadedData | LazyLoadedData] = []
        load_files(self.path)
        return loaded_files
