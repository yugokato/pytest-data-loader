from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from enum import auto
from pathlib import Path
from typing import Any, Literal, ParamSpec, Protocol, TypeAlias, TypedDict, TypeVar, runtime_checkable

from pytest import Mark, MarkDecorator

from pytest_data_loader.compat import StrEnum
from pytest_data_loader.constants import ROOT_DIR

T = TypeVar("T")
P = ParamSpec("P")
TestFunc = TypeVar("TestFunc", bound=Callable[..., Any])
JsonType: TypeAlias = str | int | float | bool | None | list["JsonType"] | dict[str, "JsonType"]
LoadedDataType: TypeAlias = JsonType | bytes | tuple[str, JsonType] | object | Iterable["LoadedDataType"]


class HashableDict(dict[str, Any]):
    """A hashable dictionary"""

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(tuple((k, HashableDict.freeze(v)) for k, v in self.items()))

    @staticmethod
    def freeze(obj: Any) -> Any:
        """Recursively convert an object to be immutable and hashable

        :param obj: Any object
        """
        if isinstance(obj, HashableDict | Mapping):
            return tuple((k, HashableDict.freeze(v)) for k, v in obj.items())
        elif isinstance(obj, tuple | Collection) and not isinstance(obj, str | bytes):
            return tuple(HashableDict.freeze(x) for x in obj)
        else:
            return obj


class DataLoaderIniOption(StrEnum):
    DATA_LOADER_DIR_NAME = auto()
    DATA_LOADER_ROOT_DIR = auto()
    DATA_LOADER_STRIP_TRAILING_WHITESPACE = auto()


@runtime_checkable
class DataLoader(Protocol):
    requires_file_path: bool
    requires_parametrization: bool
    should_split_data: bool
    __name__: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class DataLoaderPathType(StrEnum):
    FILE = auto()
    DIRECTORY = auto()


class DataLoaderFunctionType(StrEnum):
    FILE_READER_FUNC = auto()
    ONLOAD_FUNC = auto()
    PARAMETRIZER_FUNC = auto()
    FILTER_FUNC = auto()
    PROCESS_FUNC = auto()
    MARKER_FUNC = auto()
    ID_FUNC = auto()
    READ_OPTION_FUNC = auto()


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedDataABC(ABC):
    file_path: Path

    @property
    def file_name(self) -> str:
        return self.file_path.name


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedData(LoadedDataABC):
    data: LoadedDataType


@dataclass(frozen=True, kw_only=True, slots=True)
class LazyLoadedDataABC(LoadedDataABC):
    file_loader: Callable[[], LoadedData | Iterable[LoadedData]]
    post_load_hook: Callable[[], None] | None = None

    @abstractmethod
    def __repr__(self) -> str:
        """Used for generating default ID"""
        raise NotImplementedError

    @property
    def data(self: T) -> T:
        return self

    @abstractmethod
    def resolve(self) -> LoadedDataType:
        raise NotImplementedError


@dataclass(frozen=True, kw_only=True, slots=True)
class LazyLoadedData(LazyLoadedDataABC):
    def __repr__(self) -> str:
        return self.file_name

    def resolve(self) -> LoadedDataType:
        loaded_data = self.file_loader()
        if self.post_load_hook:
            self.post_load_hook()
        assert isinstance(loaded_data, LoadedData), type(loaded_data)
        return loaded_data.data


@dataclass(frozen=True, kw_only=True, slots=True)
class LazyLoadedPartData(LazyLoadedDataABC):
    idx: int
    pos: int | None = None
    # Temporarily store id and marks
    meta: dict[str, Any]

    def __repr__(self) -> str:
        return f"{self.file_name}:part{self.idx + 1}"

    def resolve(self) -> LoadedDataType:
        loaded_data = self.file_loader()
        if self.post_load_hook:
            self.post_load_hook()

        if isinstance(loaded_data, LoadedData):
            part_data = loaded_data
        else:
            assert isinstance(loaded_data, list), type(loaded_data)
            part_data = loaded_data[self.idx]
            assert isinstance(part_data, LoadedData), type(part_data)
        return part_data.data


@dataclass(frozen=True, kw_only=True, slots=True)
class DataLoaderLoadAttrs:
    """Data loader attributes added for a test function that uses a data loader decorator"""

    loader: DataLoader
    fixture_names: tuple[str, ...]
    relative_path: Path
    lazy_loading: bool = True
    file_reader: Callable[..., Iterable[Any] | object] | None = None
    file_reader_func: Callable[[Path], Callable[..., Iterable[Any] | object]] | None = None
    onload_func: Callable[..., Any] | None = None
    parametrizer_func: Callable[..., Iterable[Any]] | None = None
    filter_func: Callable[..., bool] | None = None
    process_func: Callable[..., Any] | None = None
    marker_func: Callable[..., MarkDecorator | Collection[MarkDecorator | Mark] | None] | None = None
    id_func: Callable[..., Any] | None = None
    read_option_func: Callable[[Path], FileReadOptions | dict[str, Any]] | None = None
    read_options: HashableDict = field(default_factory=HashableDict)

    def __post_init__(self) -> None:
        self._validate_fixture_names()
        self._validate_relative_path()
        self._validate_file_reader(self.file_reader)
        self._validate_loader_func()
        self._validate_read_options(self.read_options)

    @property
    def requires_file_path(self) -> bool:
        return len(self.fixture_names) == 2

    def _validate_fixture_names(self) -> None:
        from pytest_data_loader.utils import is_valid_fixture_name

        orig_value = self.fixture_names
        if not isinstance(orig_value, (str, tuple)):
            raise TypeError(f"fixture_names: Expected a string or tuple, but got {type(orig_value).__name__!r}")
        if isinstance(orig_value, tuple) and not all(isinstance(x, str) for x in orig_value):
            raise TypeError(
                f"fixture_names: Expected a tuple of strings, but got {type(orig_value).__name__} "
                f"with element types {[type(v).__name__ for v in orig_value]}."
            )

        if isinstance(orig_value, str):  # type: ignore
            normalized_names = tuple(x.strip() for x in orig_value.split(","))  # type: ignore
        else:
            normalized_names = tuple(orig_value)

        err = "Invalid fixture_names value"
        if not all(is_valid_fixture_name(x) for x in normalized_names):
            raise ValueError(f"{err}: One or more values are illegal: {orig_value!r}")

        len_names = len(normalized_names)
        if not 0 < len(normalized_names) < 3:
            raise ValueError(f"{err}: It must be either 1 or 2 fixture names. Got {len_names}: {orig_value!r}")

        self._modify_value("fixture_names", normalized_names)

    def _validate_relative_path(self) -> None:
        orig_value = self.relative_path
        if not isinstance(orig_value, Path | str):
            raise TypeError(f"relative_path: Expected a string or pathlib.Path, but got {type(orig_value).__name__!r}")

        self._modify_value("relative_path", Path(orig_value))
        err = "Invalid relative_path value"
        if self.relative_path in (Path("."), Path(".."), ROOT_DIR):
            raise ValueError(f"{err}: {orig_value!r}")
        if self.relative_path.is_absolute():
            raise ValueError(f"{err}: It can not be an absolute path: {orig_value!r}")

    @staticmethod
    def _validate_file_reader(file_reader: Any | None) -> None:
        if file_reader:
            if not (
                (isinstance(file_reader, type) and issubclass(file_reader, Iterable))
                or callable(file_reader)
                or hasattr(file_reader, "__iter__")
            ):
                got = file_reader if isinstance(file_reader, type) else type(file_reader)
                raise TypeError(f"file_reader: Expected an iterable or a callable, but got {got.__name__!r}")

    def _validate_loader_func(self) -> None:
        from pytest_data_loader import parametrize_dir
        from pytest_data_loader.utils import validate_loader_func_args_and_normalize

        for f, func_type in [
            (self.file_reader_func, DataLoaderFunctionType.FILE_READER_FUNC),
            (self.onload_func, DataLoaderFunctionType.ONLOAD_FUNC),
            (self.parametrizer_func, DataLoaderFunctionType.PARAMETRIZER_FUNC),
            (self.filter_func, DataLoaderFunctionType.FILTER_FUNC),
            (self.process_func, DataLoaderFunctionType.PROCESS_FUNC),
            (self.marker_func, DataLoaderFunctionType.MARKER_FUNC),
            (self.id_func, DataLoaderFunctionType.ID_FUNC),
            (self.read_option_func, DataLoaderFunctionType.READ_OPTION_FUNC),
        ]:
            if f is not None:
                if not callable(f):
                    raise TypeError(f"{func_type}: Must be a callable, not {type(f).__name__!r}")
                with_file_path_only = self.loader == parametrize_dir and func_type in (
                    DataLoaderFunctionType.FILE_READER_FUNC,
                    DataLoaderFunctionType.FILTER_FUNC,
                    DataLoaderFunctionType.MARKER_FUNC,
                    DataLoaderFunctionType.READ_OPTION_FUNC,
                )
                self._modify_value(
                    func_type,
                    validate_loader_func_args_and_normalize(
                        f, func_type=func_type, with_file_path_only=with_file_path_only
                    ),
                )

    @staticmethod
    def _validate_read_options(read_options: FileReadOptions | dict[str, Any]) -> None:
        if not isinstance(read_options, dict):
            raise TypeError(f"read_options: Expected a dict, but got {type(read_options).__name__!r}")
        if unsupported := set(read_options.keys()).difference(set(FileReadOptions.__annotations__.keys())):
            raise ValueError(f"Unsupported read options: {', '.join(unsupported)}")
        if (mode := read_options.get("mode")) and mode not in ("r", "rt", "rb"):
            raise ValueError(f"read_options: Invalid read mode: {mode}")

    def _modify_value(self, field_name: str, new_value: Any) -> None:
        object.__setattr__(self, field_name, new_value)


class FileReadOptions(TypedDict, total=False):
    mode: Literal["r", "rt", "rb"]
    encoding: str
    errors: Literal[
        "strict", "ignore", "replace", "surrogateescape", "xmlcharrefreplace", "backslashreplace", "namereplace"
    ]
    newline: Literal[None, "", "\n", "\r", "\r\n"]
