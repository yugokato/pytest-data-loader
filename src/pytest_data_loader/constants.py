from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pytest import StashKey

if TYPE_CHECKING:
    from pytest_data_loader.types import DataLoaderOption


DEFAULT_LOADER_DIR_NAME = "data"
PYTEST_DATA_LOADER_ATTRS = "_pytest_data_loader_attrs"
PYTEST_DATA_LOADER_MODULE_CACHE = "_pytest_data_loader_module_cache"
ROOT_DIR = Path(".").resolve().anchor
STASH_KEY_DATA_LOADER_OPTION: StashKey[DataLoaderOption] = StashKey()
