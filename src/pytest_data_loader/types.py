from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from enum import auto
from pathlib import Path
from typing import Any, Protocol, TypeAlias, TypeVar, runtime_checkable

from pytest import Mark, MarkDecorator

from pytest_data_loader.compat import StrEnum
from pytest_data_loader.constants import ROOT_DIR

T = TypeVar("T")
TestFunc = TypeVar("TestFunc", bound=Callable[..., Any])
JsonType: TypeAlias = str | int | float | bool | None | list["JsonType"] | dict[str, "JsonType"]
LoadedDataType: TypeAlias = JsonType | bytes | tuple[str, JsonType] | Iterable["LoadedDataType"]


class DataLoaderIniOption(StrEnum):
    DATA_LOADER_DIR_NAME = auto()
    DATA_LOADER_ROOT_DIR = auto()
    DATA_LOADER_STRIP_TRAILING_WHITESPACE = auto()


@runtime_checkable
class DataLoader(Protocol):
    requires_file_path: bool
    requires_parametrization: bool
    __name__: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class DataLoaderPathType(StrEnum):
    FILE = auto()
    DIRECTORY = auto()


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
    offset: int | None = None
    _marks: MarkDecorator | Collection[MarkDecorator | Mark] | None = None
    _id: Any = None

    def __repr__(self) -> str:
        return f"{self.file_name}:part{self.idx + 1}"

    def resolve(self) -> LoadedDataType:
        loaded_data = self.file_loader()
        if self.post_load_hook:
            self.post_load_hook()
        if self.offset is None:
            assert isinstance(loaded_data, tuple), type(loaded_data)
            part_data = loaded_data[self.idx]
        else:
            part_data = loaded_data
        assert isinstance(part_data, LoadedData), type(part_data)
        return part_data.data


@dataclass(frozen=True, kw_only=True, slots=True)
class DataLoaderLoadAttrs:
    """Data loader attributes added for a test function that uses a data loader decorator"""

    loader: DataLoader
    fixture_names: tuple[str, ...]
    relative_path: Path
    lazy_loading: bool = True
    force_binary: bool = False
    onload_func: Callable[..., LoadedDataType] | None = None
    parametrizer_func: Callable[..., Iterable[LoadedDataType]] | None = None
    filter_func: Callable[..., bool] | None = None
    process_func: Callable[..., LoadedDataType] | None = None
    marker_func: Callable[..., MarkDecorator | Collection[MarkDecorator | Mark] | None] | None = None
    id_func: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        self._validate_fixture_names()
        self._validate_relative_path()
        self._validate_loader_func()

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

    def _validate_loader_func(self) -> None:
        for f, name in [
            (self.onload_func, "onload_func"),
            (self.parametrizer_func, "parametrizer_func"),
            (self.filter_func, "filter_func"),
            (self.process_func, "process_func"),
            (self.marker_func, "marker_func"),
            (self.id_func, "id_func"),
        ]:
            if f and not callable(f):
                raise TypeError(f"{name}: Must be a callable, not {type(f).__name__!r}")

    def _modify_value(self, field_name: str, new_value: Any) -> None:
        object.__setattr__(self, field_name, new_value)


class UnsupportedFuncArg: ...
