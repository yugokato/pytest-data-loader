from __future__ import annotations

import json
import logging
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable
from functools import lru_cache, partial, wraps
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import Any, ClassVar, TypeVar, cast

from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    DataLoaderPathType,
    HashableDict,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
    LoadedDataType,
)
from pytest_data_loader.utils import validate_loader_func_args_and_normalize

T = TypeVar("T", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


def loader(path_type: DataLoaderPathType, /, *, parametrize: bool = False) -> Callable[[T], T]:
    """Decorator to register a decorated function as a data loader

    :param path_type: A type of the relative path it allows. file or directory
    :param parametrize: Whether the loader needs to perform parametrization or not
    """

    def wrapper(loader_func: T) -> T:
        loader_func.requires_file_path = DataLoaderPathType(path_type) == DataLoaderPathType.FILE  # type: ignore[attr-defined]
        loader_func.requires_parametrization = parametrize is True  # type: ignore[attr-defined]
        return loader_func

    return wrapper


def data_loader_factory(
    abs_data_path: Path, load_attrs: DataLoaderLoadAttrs, /, *, strip_trailing_whitespace: bool
) -> FileDataLoader | DirectoryDataLoader:
    """Data loader factory that creates either FileDataLoader or DirectoryDataLoader depending on the specified path

    :param abs_data_path: File or directory's absolute path
    :param load_attrs: Data loader attributes
    :param strip_trailing_whitespace: Whether to strip trailing whitespace from loaded data
    """
    if not abs_data_path.is_absolute():
        raise ValueError("abs_data_path must be an absolute path")

    if abs_data_path.is_file():
        return FileDataLoader(abs_data_path, load_attrs, strip_trailing_whitespace=strip_trailing_whitespace)
    else:
        return DirectoryDataLoader(abs_data_path, load_attrs, strip_trailing_whitespace=strip_trailing_whitespace)


class LoaderABC(ABC):
    def __init__(self, path: Path, load_attrs: DataLoaderLoadAttrs, strip_trailing_whitespace: bool):
        assert path.is_absolute()
        self.path = path
        self.load_attrs = load_attrs
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
        self.read_options = self.load_attrs.read_options
        self._is_streamable = all(
            [
                self.read_mode != "rb",
                self.path.suffix in FileDataLoader.STREAMABLE_FILE_TYPES,
                not any([self.load_attrs.onload_func, self.load_attrs.parametrizer_func]),
            ]
        )
        self._should_split = self.loader.requires_file_path and self.loader.requires_parametrization
        # caches used by the @parametrize loader.
        # NOTE: In Pytest, these cache data will be cleared as a module teardown managed by the plugin
        self._cached_file_objects: dict[tuple[Path, HashableDict], TextIOWrapper] = {}
        self._cached_loader_functions: set[Callable[..., Any]] = set()
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

    @property
    def should_split_data(self) -> bool:
        """Whether the file content needs to be split or not"""
        return self._should_split

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
        if self._cached_loader_functions:
            for f in self._cached_loader_functions:
                try:
                    f.cache_clear()  # type: ignore[attr-defined]
                except Exception as e:
                    logger.exception(e)
            self._cached_loader_functions.clear()

    def _parametrizer_func(self, data: LoadedDataType) -> Iterable[LoadedDataType]:
        """Default parametrizer function to apply to loaded data when parametrization is needed

        :param data: Loaded data
        """
        if isinstance(data, bytes):
            raise ValueError(f"@{self.loader.__name__} loader requires a custom parametrizer function for binary data")

        if isinstance(data, str):
            stream = StringIO(data)
            return (line.rstrip("\r\n") for line in stream)
        elif isinstance(data, dict):
            return iter(data.items())
        elif isinstance(data, Iterable):
            return iter(data)
        else:
            return iter([data])

    def _onload_func(
        self, file_path: Path, data: LoadedDataType, /, *, strip_trailing_whitespace: bool
    ) -> LoadedDataType:
        """Plugin-managed onload function that will allways be applied to the original data that has been loaded.

        :param file_path: Path to the loaded file
        :param data: Loaded data
        :param strip_trailing_whitespace: Remove trailing whitespace
        """
        if isinstance(data, str) and strip_trailing_whitespace:
            data = data.rstrip()

        if file_path.suffix == ".json":
            try:
                data = json.loads(data)  # type: ignore
            except json.decoder.JSONDecodeError as e:
                raise ValueError(f"Unable to parse JSON file: {file_path}") from e

        # TODO: Add more if needed

        return data

    def _load_now(self) -> LoadedData | Iterable[LoadedData]:
        """Load the entire file data now, then finalize the loaded data after applying all loader functions requested

        NOTE: When resolving lazily loaded part data, this function result will be dynamically cached to share it among
              all part data
        """
        raw_data = self._read_file()
        data = self._onload_func(self.path, raw_data, strip_trailing_whitespace=self.strip_trailing_whitespace)

        # Adjust the shape of data based on loader functions
        if self.load_attrs.onload_func:
            data = self.load_attrs.onload_func(self.path, data)

        if self.should_split_data:
            parametrizer_func = self.load_attrs.parametrizer_func or validate_loader_func_args_and_normalize(
                self._parametrizer_func
            )
            data = parametrizer_func(self.path, data)
            if not isinstance(data, Iterable) or isinstance(data, str | bytes):
                raise ValueError(f"Parametrized data must be an iterable container, not {type(data).__name__!r}")

            if self.load_attrs.filter_func:
                data = (x for x in data if self.load_attrs.filter_func(self.path, x))
            if self.load_attrs.process_func:
                data = (self.load_attrs.process_func(self.path, x) for x in data)
            return [LoadedData(file_path=self.path, data=x) for x in data]
        else:
            if self.load_attrs.process_func:
                data = self.load_attrs.process_func(self.path, data)
            return LoadedData(file_path=self.path, data=data)

    def _load_part_data_now(self, offset: int, /, *, close: bool = True) -> LoadedData:
        """Load part data for the offset now

        :param offset: Offset for the part data
        :param close: Close the file. Otherwise, the file object will be cached for reusing
        """
        if not self.is_streamable:
            raise NotImplementedError("Part data loading is not supported for this type of file")

        f = self._get_file_obj()
        try:
            f.seek(offset)
            line = cast(LoadedDataType, f.readline().rstrip("\r\n"))
            if self.load_attrs.process_func:
                line = self.load_attrs.process_func(self.path, line)
            return LoadedData(file_path=self.path, data=line)
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
        if self.should_split_data:
            # @parametrize() loader handles lazy loading in two different modes depending on the file type and the
            # specified load options. If certain conditions are met, we can split the file content without actually
            # loading the entire file at all. Otherwise, we fall back to the other mode
            if self.is_streamable:
                # Each line can be accessible with the offset without loading the entire file
                scan_results = self._scan_text_file()
                return [
                    LazyLoadedPartData(
                        file_path=self.path,
                        file_loader=partial(self._load_part_data_now, offset, close=False),
                        idx=i,
                        offset=offset,
                        meta=dict(marks=marks, id=param_id),
                    )
                    for i, (offset, marks, param_id) in enumerate(scan_results)
                ]
            else:
                # The entire file content needs to be loaded once during the collection phase
                # to be able to determine the number of parametrized tests by splitting the content. Once it is done,
                # we will not keep the data in memory
                # NOTE: The actual data loaded with the file loader called during a test setup will be cached and
                #       reused among tests for the same test function
                loaded_data = self._load_now()
                assert isinstance(loaded_data, list)
                file_loader = lru_cache(maxsize=1)(self._load_now)
                return [
                    LazyLoadedPartData(
                        file_path=self.path,
                        file_loader=file_loader,
                        idx=i,
                        meta=dict(
                            marks=self.load_attrs.marker_func(self.path, data.data)
                            if self.load_attrs.marker_func
                            else None,
                            id=self.load_attrs.id_func(self.path, data.data) if self.load_attrs.id_func else None,
                        ),
                        # Add the file loader to the cache when the part data is resolved
                        post_load_hook=partial(self._cached_loader_functions.add, file_loader),
                    )
                    for i, data in enumerate(loaded_data)
                ]
        else:
            return LazyLoadedData(file_path=self.path, file_loader=self._load_now)

    def _get_file_obj(self) -> TextIOWrapper:
        """Get file object from cache or open a new one"""
        f = self._cached_file_objects.get((self.path, self.read_options), open(self.path, **self.read_options))
        f.seek(0)
        return f

    def _scan_text_file(self) -> Generator[tuple[int, Any, Any]]:
        """Scan file and returns offset of each line that should be loaded.

        NOTE: The following loader functions will be applied to each line as part of the scan
        - filter_func
        - marker_func
        - id_func
        """
        assert self.is_streamable
        results = []
        buffer = []

        with open(self.path, **self.read_options) as f:
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    # EOF
                    break

                line = line.rstrip("\r\n")
                if not self.load_attrs.filter_func or self.load_attrs.filter_func(self.path, line):
                    param_id = param_marks = None
                    if self.load_attrs.marker_func:
                        param_marks = self.load_attrs.marker_func(self.path, line)
                    if self.load_attrs.id_func:
                        param_id = self.load_attrs.id_func(self.path, line)
                    if self.strip_trailing_whitespace:
                        if line.rstrip() == "":
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


class DirectoryDataLoader(LoaderABC):
    """Data loader for loading files in a directory"""

    @wraps(LoaderABC.__init__)  # type: ignore[misc]
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if self.loader.requires_file_path:
            raise NotImplementedError(f"Unsupported loader for {DirectoryDataLoader.__name__}: {self.loader}")

    def load(self) -> Iterable[LoadedData | LazyLoadedData]:  # type: ignore[override]
        """Load multiple files from a directory"""
        loaded_files = []
        for p in sorted(self.path.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                file_path = self.path / p.name
                if not self.load_attrs.filter_func or self.load_attrs.filter_func(file_path):
                    file_loader = FileDataLoader(
                        file_path, self.load_attrs, strip_trailing_whitespace=self.strip_trailing_whitespace
                    )
                    if self.load_attrs.read_func:
                        read_options = self.load_attrs.read_func(file_path) or HashableDict()
                        self.load_attrs._validate_read_options(read_options)
                        file_loader.read_options = read_options
                    loaded_data = file_loader.load()
                    assert isinstance(loaded_data, LoadedData | LazyLoadedData), type(loaded_data)
                    loaded_files.append(loaded_data)
        return loaded_files
