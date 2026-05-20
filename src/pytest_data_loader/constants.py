from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pytest import StashKey

if TYPE_CHECKING:
    from pytest_data_loader.loaders.cache import SessionFileCache
    from pytest_data_loader.types import DataLoaderOption


DEFAULT_LOADER_DIR_NAME = "data"
DEFAULT_ENCODING = "utf-8"
DEFAULT_MAX_CACHED_CONTENT_SIZE = "128MiB"
DEFAULT_MAX_OPEN_FILE_HANDLES = 64
PYTEST_DATA_LOADER_ATTRS = "_pytest_data_loader_attrs"
PYTEST_DATA_LOADER_MODULE_CACHE = "_pytest_data_loader_module_cache"
ROOT_DIR = Path(".").resolve().anchor

# Pytest stash keys
STASH_KEY_DATA_LOADER_OPTION: StashKey[DataLoaderOption] = StashKey()
STASH_KEY_FILE_CACHE: StashKey[SessionFileCache] = StashKey()
