from __future__ import annotations

import inspect
import json
from collections import defaultdict
from collections.abc import Callable, Generator
from pathlib import Path
from threading import RLock
from typing import IO, Any, ClassVar

from pytest_data_loader.types import HashableDict, ReadOptions
from pytest_data_loader.validators import validate_read_options, validate_reader

__all__ = ["register_reader"]


_LOCK = RLock()


class FileReader:
    # Store registered readers by conftest paths
    _REGISTERED_READERS: ClassVar[dict[Path, dict[str, FileReader]]] = defaultdict(dict)

    def __init__(self, reader: Callable[..., Any] | None = None, read_options: ReadOptions | None = None) -> None:
        self.reader = reader
        self.read_options = HashableDict(read_options or {})

    @staticmethod
    def register(
        conftest_path: Path, ext: str, reader: Callable[..., Any], /, read_options: ReadOptions | None = None
    ) -> FileReader:
        """Register the file reader for the file extension.

        :param conftest_path: Path to conftest.py the registration is done from
        :param ext: File extension
        :param reader: A file reader to register
        :param read_options: File read options to pass to open() when reading the file
        """
        if not ext.startswith("."):
            raise ValueError("File extension must start with '.'")

        validate_reader(reader)
        validate_read_options(read_options)

        with _LOCK:
            file_reader = FileReader(reader, read_options=read_options)
            FileReader._REGISTERED_READERS[conftest_path][ext] = file_reader
        return file_reader

    @staticmethod
    def _unregister(conftest_path: Path, ext: str) -> None:
        """Unregister the file reader for the file extension.

        :param conftest_path: Path to conftest.py the registration was done from
        :param ext: File extension
        """
        if not ext.startswith("."):
            raise ValueError("File extension must start with '.'")

        with _LOCK:
            del FileReader._REGISTERED_READERS[conftest_path][ext]

    @staticmethod
    def get_registered_reader(search_from: Path, ext: str) -> FileReader | None:
        """Returns a registered or default file reader

        :param search_from: The location to search the reader registration from
        :param ext: File extension to get a reader for
        """
        assert search_from.is_absolute()
        if search_from.is_file():
            search_from = search_from.parent

        with _LOCK:
            reader = None
            for conftest_path in sorted(
                FileReader._REGISTERED_READERS.keys(), key=lambda p: len(p.parents), reverse=True
            ):
                if search_from.is_relative_to(conftest_path.parent):
                    if reader := FileReader._REGISTERED_READERS[conftest_path].get(ext):
                        break
            return reader or _DEFAULT_READERS.get(ext)


def register_reader(
    ext: str, file_reader: Callable[..., Any], /, read_options: ReadOptions | None = None
) -> FileReader:
    """Register file reader for the given file extension.

    NOTE: This function must be called from a conftest.py. If registration is done in multiple conftest.py, the closest
          conftest.py from a test function will be effective.

    :param ext: File extension
    :param file_reader: A reader callable (e.g. csv.reader, yaml.safe_load) to register for the extension
    :param read_options: File read options to pass to open() when reading the file
    """
    caller_frame = inspect.stack()[1]
    caller_file = Path(caller_frame.filename).resolve()

    if caller_file.name != "conftest.py":
        raise RuntimeError(
            f"{__name__.split('.')[0]}.{register_reader.__name__}() must be called from a conftest.py, "
            f"not from {str(caller_file)!r}"
        )
    return FileReader.register(caller_file, ext, file_reader, read_options=read_options)


def _jsonl_reader(f: IO[str]) -> Generator[Any]:
    """Read a JSON Lines file, yielding one parsed JSON object per non-empty line.

    :param f: File object to read from
    """
    for line in f:
        stripped = line.strip()
        if stripped:
            yield json.loads(stripped)


_DEFAULT_READERS = {
    ".json": FileReader(reader=json.load),
    ".jsonl": FileReader(reader=_jsonl_reader),
}
