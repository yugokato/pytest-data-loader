from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import auto
from pathlib import Path
from typing import Any, Protocol, TypeAlias, TypeVar, runtime_checkable

from pytest_data_loader.compat import StrEnum

T = TypeVar("T")
TestFunc = TypeVar("TestFunc", bound=Callable[..., Any])
JsonType: TypeAlias = str | int | float | bool | None | list["JsonType"] | dict[str, "JsonType"]
LoadedDataType: TypeAlias = JsonType | bytes | tuple[str, JsonType] | Iterable["LoadedDataType"]


class DataLoaderIniOption(StrEnum):
    DATA_LOADER_DIR_NAME = auto()
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

    @abstractmethod
    def __repr__(self) -> str:
        """Used for generating default ID"""
        raise NotImplementedError

    @property
    def file_name(self) -> str:
        return self.file_path.name


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedData(LoadedDataABC):
    data: LoadedDataType

    def __repr__(self) -> str:
        return repr(self.data)


@dataclass(frozen=True, kw_only=True, slots=True)
class LazyLoadedDataABC(LoadedDataABC):
    file_loader: Callable[[], LoadedData | Iterable[LoadedData]]
    post_load_hook: Callable[[], None] | None = None

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

    def __repr__(self) -> str:
        return f"{self.file_name}:part{self.idx}"

    def resolve(self) -> LoadedDataType:
        loaded_data = self.file_loader()
        if self.post_load_hook:
            self.post_load_hook()
        if self.offset is None:
            assert isinstance(loaded_data, list), type(loaded_data)
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
    id_func: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        len_args = len(self.fixture_names)
        if not 0 < len(self.fixture_names) < 3:
            raise ValueError(f"The loader supports either 1 or 2 fixture names. Got {len_args}: {self.fixture_names}")

    @property
    def requires_file_path(self) -> bool:
        return len(self.fixture_names) == 2


class UnsupportedFuncArg: ...
