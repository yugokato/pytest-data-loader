from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from enum import auto
from pathlib import Path
from typing import IO, Any, Literal, ParamSpec, Protocol, TypeAlias, TypedDict, TypeVar, Union, runtime_checkable

import pytest
from pytest import Config, Mark, MarkDecorator

from pytest_data_loader.compat import StrEnum
from pytest_data_loader.exceptions import DataNotFound
from pytest_data_loader.paths import expand_env_vars, has_env_vars

T = TypeVar("T")
P = ParamSpec("P")
Func = TypeVar("Func", bound=Callable[..., Any])
JsonType: TypeAlias = str | int | float | bool | None | list["JsonType"] | dict[str, "JsonType"]
LoadedDataType: TypeAlias = JsonType | bytes | tuple[str, JsonType] | object | Iterable["LoadedDataType"]
PytestMarkType: TypeAlias = MarkDecorator | Collection[MarkDecorator | Mark]
ReadOptions: TypeAlias = Union["FileReadOptions", dict[str, Any]]

# Loader callable option types
FileReader: TypeAlias = Callable[[IO[Any]], Any]
OnloadFunc: TypeAlias = Callable[[Any], Any] | Callable[[Path, Any], Any]
ParametrizerFunc: TypeAlias = Callable[[Any], Iterable[Any]] | Callable[[Path, Any], Iterable[Any]]
FilterFunc: TypeAlias = Callable[[Any], bool] | Callable[[Path, Any], bool]
ProcessorFunc: TypeAlias = Callable[[Any], Any] | Callable[[Path, Any], Any] | Callable[[int, Path, Any], Any]
MarkerFunc: TypeAlias = (
    Callable[[Any], PytestMarkType | None]
    | Callable[[Path, Any], PytestMarkType | None]
    | Callable[[int, Path, Any], PytestMarkType | None]
)
IdFunc: TypeAlias = (
    Callable[[Any], str | None] | Callable[[Path, Any], str | None] | Callable[[int, Path, Any], str | None]
)
ReaderFunc: TypeAlias = Callable[[Path], FileReader] | Callable[[int, Path], FileReader]
ReadOptionsFunc: TypeAlias = Callable[[Path], ReadOptions] | Callable[[int, Path], ReadOptions]
PathFilterFunc: TypeAlias = Callable[[Path], bool]
PathMarkerFunc: TypeAlias = Callable[[Path], PytestMarkType | None] | Callable[[int, Path], PytestMarkType | None]
PathIdFunc: TypeAlias = Callable[[Path], str | None] | Callable[[int, Path], str | None]


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


class DataLoaderType(StrEnum):
    LOAD = auto()
    PARAMETRIZE = auto()
    PARAMETRIZE_DIR = auto()


class DataLoaderIniOption(StrEnum):
    DATA_LOADER_DIR_NAME = auto()
    DATA_LOADER_ROOT_DIR = auto()
    DATA_LOADER_STRIP_TRAILING_WHITESPACE = auto()
    DATA_LOADER_ON_MISSING = auto()


class DataLoaderOnMissingAction(StrEnum):
    """How to behave when a configured data path cannot be located."""

    RAISE = auto()
    SKIP = auto()
    XFAIL = auto()
    WARN = auto()


class DataLoaderOption:
    """Parsed pytest-data-loader INI options for the current session."""

    def __init__(self, config: Config):
        """Parse and validate all INI options.

        :param config: The pytest Config object for the current session.
        """
        self._config = config
        self.loader_dir_name = self._parse_ini_option(DataLoaderIniOption.DATA_LOADER_DIR_NAME)
        self.loader_root_dir = self._parse_ini_option(DataLoaderIniOption.DATA_LOADER_ROOT_DIR)
        self.strip_trailing_whitespace = self._parse_ini_option(
            DataLoaderIniOption.DATA_LOADER_STRIP_TRAILING_WHITESPACE
        )
        self.on_missing = self._parse_ini_option(DataLoaderIniOption.DATA_LOADER_ON_MISSING)

    def _parse_ini_option(self, option: DataLoaderIniOption) -> str | bool | Path:
        """Parse pytest INI option and perform additional validation if needed.

        :param option: INI option
        """
        try:
            v = self._config.getini(option)
            if option == DataLoaderIniOption.DATA_LOADER_DIR_NAME:
                assert isinstance(v, str)
                if v in ("", ".", "..") or os.sep in v:
                    raise ValueError(rf"Invalid value: '{v}'")
            elif option == DataLoaderIniOption.DATA_LOADER_ROOT_DIR:
                assert isinstance(v, str)
                orig_value = v
                pytest_rootdir = self._config.rootpath
                if v == "":
                    return pytest_rootdir
                if has_env_vars(v):
                    v = expand_env_vars(v)
                v = Path(os.path.expanduser(v))
                if not v.is_absolute():
                    v = v.resolve()

                err = None
                if not v.exists():
                    err = "The specified path does not exist"
                elif v.is_file():
                    err = "The path must be a directory"
                elif not pytest_rootdir.is_relative_to(v):
                    err = "The path must be one of the parent directories of pytest rootdir"
                elif v.is_relative_to(pytest_rootdir):
                    err = "The path must be outside the pytest rootdir"
                if err:
                    err += f": {orig_value!r}"
                    if orig_value != str(v):
                        err += f" (resolved value: {str(v)!r})"
                    raise ValueError(err)
            elif option == DataLoaderIniOption.DATA_LOADER_ON_MISSING:
                assert isinstance(v, str)
                allowed = [m.value for m in DataLoaderOnMissingAction]
                if v not in allowed:
                    raise ValueError(f"Invalid value: '{v}'. Must be one of: {', '.join(repr(x) for x in allowed)}")
                return DataLoaderOnMissingAction(v)
            return v
        except ValueError as e:
            raise pytest.UsageError(f"INI option {option}: {e}") from e


@runtime_checkable
class DataLoader(Protocol):
    is_data_loader: bool
    type: DataLoaderType
    is_file_loader: bool
    requires_parametrization: bool
    should_split_data: bool
    __name__: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
    def __hash__(self) -> int: ...


class DataLoaderSource(StrEnum):
    FILE = auto()
    DIRECTORY = auto()


class DataLoaderFunctionType(StrEnum):
    ONLOAD_FUNC = auto()
    PARAMETRIZER_FUNC = auto()
    FILTER_FUNC = auto()
    PROCESS_FUNC = auto()
    READER_FUNC = auto()
    READ_OPTIONS_FUNC = auto()
    MARKER_FUNC = auto()
    ID_FUNC = auto()

    @property
    def public_name(self) -> str:
        """Return the public-facing name for this enum member"""
        return _LOADER_FUNC_PUBLIC_NAMES[self]

    @classmethod
    def _validate(cls) -> None:
        missing = [member for member in cls if member not in _LOADER_FUNC_PUBLIC_NAMES]
        if missing:
            raise RuntimeError(f"Missing public name mapping for: {missing}")


_LOADER_FUNC_PUBLIC_NAMES = {
    DataLoaderFunctionType.ONLOAD_FUNC: "onload",
    DataLoaderFunctionType.PARAMETRIZER_FUNC: "parametrizer",
    DataLoaderFunctionType.FILTER_FUNC: "filter",
    DataLoaderFunctionType.PROCESS_FUNC: "processor",
    DataLoaderFunctionType.MARKER_FUNC: "marks",
    DataLoaderFunctionType.ID_FUNC: "ids",
    DataLoaderFunctionType.READER_FUNC: "reader",
    DataLoaderFunctionType.READ_OPTIONS_FUNC: "read_options",
}
DataLoaderFunctionType._validate()


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class Data(ABC):
    gidx: int | None = None
    file_path: Path
    loaded_from: Path | None = None

    def __repr__(self) -> str:
        return str(self.file_path_relative or self.file_path)

    @property
    def file_name(self) -> str:
        return self.file_path.name

    @property
    def file_path_relative(self) -> Path | None:
        if self.loaded_from:
            return self.file_path.relative_to(self.loaded_from)
        return None


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class MissingData(Data):
    error: DataNotFound

    def __repr__(self) -> str:
        return f"{Data.__repr__(self)}:MISSING"

    @property
    def data(self) -> None:
        return None


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class LoadedData(Data):
    data: LoadedDataType


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class LazyLoadedDataABC(Data):
    resolver: Callable[..., LoadedData | Iterable[LoadedData]]

    @property
    def data(self: T) -> T:
        return self

    @abstractmethod
    def resolve(self) -> LoadedDataType:
        raise NotImplementedError


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class LazyLoadedData(LazyLoadedDataABC):
    def resolve(self) -> LoadedDataType:
        loaded_data = self.resolver()
        assert isinstance(loaded_data, LoadedData), type(loaded_data)
        return loaded_data.data


@dataclass(frozen=True, kw_only=True, slots=True, repr=False)
class LazyLoadedPartData(LazyLoadedDataABC):
    idx: int
    pos: int | None = None
    # Temporarily store id and marks
    meta: dict[str, Any]

    def __repr__(self) -> str:
        parent_dir = (self.file_path_relative or self.file_path).parent
        return str(parent_dir / f"{self.file_name}:part{self.idx + 1}")

    def resolve(self) -> LoadedDataType:
        loaded_data = self.resolver()
        assert isinstance(loaded_data, LoadedData)
        return loaded_data.data


@dataclass(frozen=True, kw_only=True, slots=True)
class DataLoaderLoadAttrs:
    """Data loader attributes added for a test function that uses a data loader decorator"""

    loader: DataLoader
    search_from: Path
    fixture_names: tuple[str, ...]
    path: Path | tuple[Path, ...]
    lazy_loading: bool = True
    recursive: bool = False
    reader: FileReader | None = None
    read_options: HashableDict = field(default_factory=HashableDict)
    onload_func: Callable[..., Any] | None = None
    parametrizer_func: Callable[..., Iterable[Any]] | None = None
    filter_func: Callable[..., bool] | None = None
    process_func: Callable[..., Any] | None = None
    reader_func: Callable[..., FileReader] | None = None
    read_options_func: Callable[..., ReadOptions] | None = None
    marker_func: Callable[..., PytestMarkType | None] | None = None
    id_func: Callable[..., Any] | None = None
    ids: tuple[Any, ...] | None = None

    @property
    def requires_file_path(self) -> bool:
        """Return True if two fixture names are configured, meaning the file path is passed as a separate fixture."""
        return len(self.fixture_names) == 2

    def __post_init__(self) -> None:
        from pytest_data_loader.utils import normalize_loader_func
        from pytest_data_loader.validators import validate_loader_func

        for f, func_type in [
            (self.onload_func, DataLoaderFunctionType.ONLOAD_FUNC),
            (self.parametrizer_func, DataLoaderFunctionType.PARAMETRIZER_FUNC),
            (self.filter_func, DataLoaderFunctionType.FILTER_FUNC),
            (self.process_func, DataLoaderFunctionType.PROCESS_FUNC),
            (self.reader_func, DataLoaderFunctionType.READER_FUNC),
            (self.read_options_func, DataLoaderFunctionType.READ_OPTIONS_FUNC),
            (self.marker_func, DataLoaderFunctionType.MARKER_FUNC),
            (self.id_func, DataLoaderFunctionType.ID_FUNC),
        ]:
            if f is not None:
                len_func_args = validate_loader_func(f, loader=self.loader, func_type=func_type)
                object.__setattr__(
                    self, func_type, normalize_loader_func(self.loader, f, func_type, num_defined_args=len_func_args)
                )


class FileReadOptions(TypedDict, total=False):
    mode: Literal["r", "rt", "rb", None]
    encoding: str | None
    errors: Literal[
        "strict", "ignore", "replace", "surrogateescape", "xmlcharrefreplace", "backslashreplace", "namereplace", None
    ]
    newline: Literal["", "\n", "\r", "\r\n", None]
