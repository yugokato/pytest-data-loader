import gc
import gzip
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.loaders.cache import CacheKey, SessionFileCache
from pytest_data_loader.loaders.impl import FileLoader
from pytest_data_loader.paths import SUPPORTED_COMPRESSION_EXTENSIONS, compression_aware_open, get_effective_suffix
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    HashableDict,
    LazyLoadedData,
    LazyLoadedPartData,
    LoadedData,
)
from tests.paths import (
    ABS_PATH_LOADER_DIR,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_GZ,
    PATH_LATIN1_TEXT_FILE,
    PATH_TEXT_FILE,
    PATH_TEXT_FILE_GZ,
    PATH_UTF16_TEXT_FILE,
    PATH_XML_FILE,
    PATHS_BINARY_FILES,
    PATHS_COMPRESSED_BINARY_FILES,
    PATHS_COMPRESSED_TEXT_FILES,
    PATHS_TEXT_FILES,
)

pytestmark = pytest.mark.unittest


class TestFileLoader:
    """Tests for file loader with various file types and loading modes."""

    @pytest.mark.parametrize("is_abs_path", [False, True])
    @pytest.mark.parametrize(
        "path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES, *PATHS_COMPRESSED_TEXT_FILES, *PATHS_COMPRESSED_BINARY_FILES]
    )
    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
    def test_file_loader(self, loader: DataLoader, lazy_loading: bool, path: Path, is_abs_path: bool) -> None:
        """Test file loader with various file types and with/without lazy loading"""
        abs_file_path = ABS_PATH_LOADER_DIR / path
        if is_abs_path:
            path = abs_file_path
            load_from = None
        else:
            load_from = ABS_PATH_LOADER_DIR
        if loader == parametrize_dir:
            path = path.parent
        is_binary = abs_file_path.relative_to(ABS_PATH_LOADER_DIR) in (
            *PATHS_BINARY_FILES,
            *PATHS_COMPRESSED_BINARY_FILES,
        )
        marks = (pytest.mark.foo, pytest.mark.bar)
        load_attrs = DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=path,
            lazy_loading=lazy_loading,
            parametrizer_func=(lambda x: [x]) if is_binary else None,
            # for @parametrize loader with lazy loading
            id_func=lambda i, *_: str(i),
            marker_func=lambda _: marks,
        )

        file_loader = FileLoader(abs_file_path, load_attrs, load_from=load_from, strip_trailing_whitespace=True)
        if get_effective_suffix(abs_file_path) == ".json":
            assert file_loader.file_reader is not None
        loaded_data = file_loader.load()

        if lazy_loading:
            if loader == parametrize:
                assert isinstance(loaded_data, list)
                for i, lazy_loaded_part in enumerate(loaded_data):
                    assert isinstance(lazy_loaded_part, LazyLoadedPartData)
                    assert lazy_loaded_part.file_path == abs_file_path
                    assert lazy_loaded_part.idx == i
                    if file_loader.is_streamable:
                        assert lazy_loaded_part.pos is not None
                        assert lazy_loaded_part.pos >= 0
                    else:
                        assert lazy_loaded_part.pos is None
                    if is_abs_path:
                        assert lazy_loaded_part.file_path_relative is None
                        assert repr(lazy_loaded_part) == f"{abs_file_path}:part{lazy_loaded_part.idx + 1}"
                    else:
                        assert lazy_loaded_part.file_path_relative == abs_file_path.relative_to(ABS_PATH_LOADER_DIR)
                        assert (
                            repr(lazy_loaded_part)
                            == f"{lazy_loaded_part.file_path_relative}:part{lazy_loaded_part.idx + 1}"
                        )
                    assert set(lazy_loaded_part.meta.keys()) == {"marks", "id"}
                    assert lazy_loaded_part.meta["id"] == str(i)
                    assert lazy_loaded_part.meta["marks"] == marks
            else:
                assert isinstance(loaded_data, LazyLoadedData)
                assert loaded_data.file_path == abs_file_path
                if is_abs_path:
                    assert loaded_data.file_path_relative is None
                    assert repr(loaded_data) == str(abs_file_path)
                else:
                    assert loaded_data.file_path_relative == loaded_data.file_path.relative_to(ABS_PATH_LOADER_DIR)
                    assert repr(loaded_data) == str(loaded_data.file_path_relative)
        else:
            if loader == parametrize:
                assert isinstance(loaded_data, list)
                for loaded_part in loaded_data:
                    assert isinstance(loaded_part, LoadedData)
                    assert loaded_part.file_path == abs_file_path
            else:
                assert isinstance(loaded_data, LoadedData)
                assert loaded_data.file_path == abs_file_path

    @pytest.mark.parametrize("data", ["test", b"\x00\x01\x02"])
    def test_read_mode_detection(self, tmp_path: Path, data: str | bytes) -> None:
        """Test that file loading can detect the file read mode"""
        abs_file_path = tmp_path / "file.bin"
        if isinstance(data, bytes):
            abs_file_path.write_bytes(data)
            expected_mode = "rb"
        else:
            abs_file_path.write_text(data)
            expected_mode = "r"

        load_attrs = DataLoaderLoadAttrs(
            loader=load, search_from=Path(__file__), fixture_names=("data",), path=abs_file_path, lazy_loading=False
        )
        file_loader = FileLoader(abs_file_path, load_attrs)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == data
        assert file_loader.read_mode == expected_mode

    def test_file_loading_with_non_default_encoding(self) -> None:
        """Test that FileLoader reads a Latin-1 encoded file correctly when default_encoding is set to latin-1"""
        encoding = "latin-1"
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_LATIN1_TEXT_FILE
        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=False,
        )
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=encoding)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == abs_file_path.read_text(encoding=encoding)
        assert file_loader.read_mode == "r"
        assert file_loader.default_encoding == encoding

    def test_file_loading_with_utf16_encoding(self) -> None:
        """Test that FileLoader reads a UTF-16 encoded file correctly when default_encoding is set to utf-16"""
        encoding = "utf-16"
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_UTF16_TEXT_FILE
        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=False,
        )
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=encoding)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == abs_file_path.read_text(encoding=encoding)
        assert file_loader.read_mode == "r"
        assert file_loader.default_encoding == encoding

    def test_file_loading_with_non_utf8_file(self) -> None:
        """Test that with the default utf-8 encoding, a non-utf-8 file is auto-detected as binary"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_LATIN1_TEXT_FILE
        load_attrs = DataLoaderLoadAttrs(
            loader=load, search_from=Path(__file__), fixture_names=("data",), path=abs_file_path, lazy_loading=False
        )
        file_loader = FileLoader(abs_file_path, load_attrs)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == abs_file_path.read_bytes()
        assert file_loader.read_mode == "rb"

    def test_file_loading_with_utf16_file(self) -> None:
        """Test that with the default utf-8 encoding, a UTF-16 file is auto-detected as binary"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_UTF16_TEXT_FILE
        load_attrs = DataLoaderLoadAttrs(
            loader=load, search_from=Path(__file__), fixture_names=("data",), path=abs_file_path, lazy_loading=False
        )
        file_loader = FileLoader(abs_file_path, load_attrs)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == abs_file_path.read_bytes()
        assert file_loader.read_mode == "rb"

    @pytest.mark.parametrize("is_default_encoding", [False, True])
    @pytest.mark.parametrize("encoding", ["utf-8", "latin-1", "ascii"])
    def test_single_byte_encoding_is_streamable(self, encoding: str, is_default_encoding: bool) -> None:
        """Test that @parametrize over a plain text file is streamable with single-byte encodings"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
        if is_default_encoding:
            default_encoding = encoding
            read_options = {}
        else:
            default_encoding = None
            read_options = {"encoding": encoding}
        load_attrs = DataLoaderLoadAttrs(
            loader=parametrize,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=True,
            read_options=HashableDict(read_options),
        )
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=default_encoding)
        assert file_loader.is_streamable

    @pytest.mark.parametrize("is_default_encoding", [False, True])
    @pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
    def test_multi_byte_encoding_is_not_streamable(self, encoding: str, is_default_encoding: bool) -> None:
        """Test that a multibyte encoding file with @parametrize is not streamable to avoid BOM/seek incompatibility"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_UTF16_TEXT_FILE
        if is_default_encoding:
            default_encoding = encoding
            read_options = {}
        else:
            default_encoding = None
            read_options = {"encoding": encoding}
        load_attrs = DataLoaderLoadAttrs(
            loader=parametrize,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=True,
            read_options=HashableDict(read_options),
        )
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=default_encoding)
        assert not file_loader.is_streamable

    @pytest.mark.parametrize("is_default_encoding", [False, True])
    def test_utf16_parametrize_loads_lines_correctly(self, is_default_encoding: bool) -> None:
        """Test that @parametrize over a UTF-16 file loads line-split content correctly"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_UTF16_TEXT_FILE
        encoding = "utf-16"
        if is_default_encoding:
            default_encoding = encoding
            read_options = {}
        else:
            default_encoding = None
            read_options = {"encoding": encoding}
        load_attrs = DataLoaderLoadAttrs(
            loader=parametrize,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=False,
            read_options=HashableDict(read_options),
        )

        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=default_encoding)
        result = file_loader.load()
        assert isinstance(result, list)
        expected = abs_file_path.read_text(encoding=encoding).rstrip().splitlines()
        assert [r.data for r in result] == expected

    def test_read_options_encoding_takes_precedence_over_default_encoding(self) -> None:
        """Test that encoding in read_options takes precedence over default_encoding (the INI option)."""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_LATIN1_TEXT_FILE
        encoding = "latin-1"
        default_encoding = "utf-16"
        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=False,
            read_options=HashableDict({"encoding": encoding}),
        )
        # utf-16 as default_encoding is incompatible with the latin-1 file; if it were used instead
        # of the read_options encoding the file would load incorrectly or raise an error
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=default_encoding)
        loaded_data = file_loader.load()

        assert isinstance(loaded_data, LoadedData)
        assert loaded_data.data == abs_file_path.read_text(encoding=encoding)
        assert file_loader.default_encoding == default_encoding
        assert file_loader.read_mode == "r"

    @pytest.mark.parametrize("is_default_encoding", [False, True])
    def test_encoding_mismatch_raises_error_with_context(self, is_default_encoding: bool) -> None:
        """Test that loading a file incompatible with the configured encoding raises a UnicodeDecodeError with
        additional context
        """
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
        encoding = "utf-16"
        if is_default_encoding:
            default_encoding = encoding
            read_options = {}
        else:
            default_encoding = None
            read_options = {"encoding": encoding}
        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=abs_file_path,
            lazy_loading=False,
            read_options=HashableDict(read_options),
        )
        file_loader = FileLoader(abs_file_path, load_attrs, default_encoding=default_encoding)
        with pytest.raises(UnicodeDecodeError, match=r".*While reading .* with options: *"):
            file_loader.load()


class TestFileLoaderCaching:
    """Tests for FileLoader cache state management across loading modes"""

    def _make_load_attrs(
        self,
        loader: DataLoader,
        path: Path,
        lazy_loading: bool = True,
        parametrizer: Callable[..., Any] | None = None,
    ) -> DataLoaderLoadAttrs:
        """Create a minimal DataLoaderLoadAttrs for testing.

        :param loader: The data loader to use
        :param path: Relative path to the test data file
        :param lazy_loading: Whether to use lazy loading
        :param parametrizer: Optional parametrizer function (e.g. for binary files)
        """
        return DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=path,
            lazy_loading=lazy_loading,
            parametrizer_func=parametrizer,
        )

    @pytest.mark.parametrize(
        "path", [*PATHS_TEXT_FILES, *PATHS_BINARY_FILES, *PATHS_COMPRESSED_TEXT_FILES, *PATHS_COMPRESSED_BINARY_FILES]
    )
    @pytest.mark.parametrize("loader", [load, parametrize, parametrize_dir])
    def test_lazy_loading_cache_state_transitions(self, loader: DataLoader, path: Path) -> None:
        """Test that lazy loading correctly transitions cache state before and after resolve and clear_cache."""
        abs_file_path = ABS_PATH_LOADER_DIR / path
        binary_files = (*PATHS_BINARY_FILES, *PATHS_COMPRESSED_BINARY_FILES)
        parametrizer: Callable[..., Any] | None = (lambda x: [x]) if path in binary_files else None
        load_attrs = self._make_load_attrs(loader, path, lazy_loading=True, parametrizer=parametrizer)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        if get_effective_suffix(abs_file_path) == ".json":
            assert file_loader.file_reader is not None

        lazy_loaded_data = file_loader._load_lazily()

        # Non-streamable @parametrize files call _load_now() once at collection (to count items). When a
        # file_reader is present, _load_now() opens the handle via _get_file_obj(), populating _file_handles.
        # All other paths leave _file_handles empty. _loaded_data is never set at collection (data is discarded).
        if loader == parametrize and not file_loader.is_streamable and file_loader.file_reader is not None:
            assert len(file_loader._file_handles) == 1
        else:
            assert file_loader._file_handles == []
        # Read into locals so mypy narrows the local, not the attribute (the attribute is mutated later).
        loaded_before = file_loader._loaded_data
        assert loaded_before is None

        if loader == parametrize:
            assert isinstance(lazy_loaded_data, list)
            for i, lazy_data in enumerate(lazy_loaded_data):
                assert isinstance(lazy_data, LazyLoadedPartData)
                lazy_data.resolve()
                if file_loader.is_streamable:
                    # Streamable: _get_file_obj opens the handle; _loaded_data stays None (direct _load_part_data_now
                    # path, not _load_now).
                    assert len(file_loader._file_handles) == 1
                    assert file_loader._loaded_data is None
                else:
                    # Non-streamable: first resolve calls _load_now with cache=True, populating _loaded_data.
                    # Subsequent resolves reuse it. _get_file_obj runs only when a file_reader is present.
                    assert file_loader._loaded_data is not None
                    if file_loader.file_reader is not None:
                        assert len(file_loader._file_handles) == 1
                    else:
                        assert len(file_loader._file_handles) == 0
        else:
            assert isinstance(lazy_loaded_data, LazyLoadedData)
            lazy_loaded_data.resolve()
            # @load and @parametrize_dir: resolve calls _load_now with cache=True, populating _loaded_data.
            assert file_loader._loaded_data is not None

        # clear_cache resets _loaded_data and closes the open file handle.
        file_loader.clear_cache()
        assert file_loader._file_handles == []
        assert file_loader._loaded_data is None

    def test_eager_loading_has_no_data_cache(self) -> None:
        """Test that eager loading does not populate the loaded-data cache for a plain text file."""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
        load_attrs = self._make_load_attrs(load, PATH_TEXT_FILE, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert file_loader.file_reader is None

        file_loader.load()

        assert file_loader._loaded_data is None
        assert file_loader._file_handles == []

    def test_eager_loading_with_file_reader_caches_file_obj(self) -> None:
        """Test that eager loading with a file_reader caches the open file handle in _file_handles"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_ARRAY, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert file_loader.file_reader is not None

        file_loader.load()

        assert file_loader._loaded_data is None
        assert len(file_loader._file_handles) == 1
        assert not file_loader._file_handles[0].closed

        file_loader.clear_cache()
        assert file_loader._file_handles == []

    def test_clear_cache_closes_file_reader_handle_when_session_cache_present(self) -> None:
        """Test that clear_cache() closes per-instance file_reader handles even when a session cache is present."""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_ARRAY, lazy_loading=True)
        file_loader = FileLoader(
            abs_file_path,
            load_attrs,
            load_from=ABS_PATH_LOADER_DIR,
            file_cache=SessionFileCache(),
        )
        assert file_loader.file_reader is not None

        lazy_data = file_loader._load_lazily()
        assert isinstance(lazy_data, LazyLoadedData)
        lazy_data.resolve()

        # file_reader causes a per-instance handle to be opened (pool is bypassed for file_reader)
        assert len(file_loader._file_handles) == 1
        handle = file_loader._file_handles[0]
        assert not handle.closed

        file_loader.clear_cache()

        assert handle.closed, (
            "Per-instance file_reader handle must be closed by clear_cache() regardless of session cache"
        )
        assert file_loader._file_handles == []

    def test_non_streamable_parametrize_lazy_double_load(self) -> None:
        """Test that non-streamable @parametrize lazy loading reads the file twice:
        once at collection (to count parametrized items) and once at first test setup
        (_loaded_data cache miss), then reuses the _loaded_data cache for subsequent resolves.
        """
        # XML has no registered file_reader and a non-streamable suffix.
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_XML_FILE
        load_attrs = self._make_load_attrs(parametrize, PATH_XML_FILE, lazy_loading=True)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert not file_loader.is_streamable
        assert file_loader.file_reader is None

        # Count actual file reads. The _loaded_data cache guard lives inside _load_now (before
        # _read_file), so _load_now still runs on every resolve but short-circuits internally;
        # counting _read_file measures genuine (re)loads.
        read_count = 0
        original_read_file = file_loader._read_file

        def counting_read_file() -> str | bytes:
            """Counting wrapper around the original _read_file."""
            nonlocal read_count
            read_count += 1
            return original_read_file()

        file_loader._read_file = counting_read_file

        # Collection phase: _read_file is called once to determine item count.
        # _loaded_data stays None because the collection-time result is not cached.
        lazy_parts = file_loader._load_lazily()
        assert isinstance(lazy_parts, list)
        assert len(lazy_parts) > 1
        assert read_count == 1, "Expected exactly one file read during collection"
        # Read into a local to narrow the local without narrowing the attribute (which is mutated later).
        loaded_after_collection = file_loader._loaded_data
        assert loaded_after_collection is None

        # First resolve: _loaded_data cache miss — the file is read a second time and cached.
        lazy_parts[0].resolve()
        assert read_count == 2, "Expected a second file read on first resolve (_loaded_data cache miss)"
        assert file_loader._loaded_data is not None
        cached_obj_id = id(file_loader._loaded_data)

        # Second resolve: _loaded_data cache hit — no additional file read, same cached object reused.
        lazy_parts[1].resolve()
        assert read_count == 2, "Expected no additional file read on second resolve (_loaded_data cache hit)"
        assert id(file_loader._loaded_data) == cached_obj_id

        file_loader.clear_cache()

    def test_file_reader_parametrize_lazy_is_non_streamable(self) -> None:
        """Test that @parametrize lazy loading with a file_reader uses the non-streamable path.

        Files with a file_reader are always non-streamable: is_streamable is False, lazy parts
        carry pos=None (index-based, not byte-offset), resolve correctly via _load_now, and
        _loaded_data is populated after first resolve and reused without re-opening the file.
        """
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(parametrize, PATH_JSON_FILE_ARRAY, lazy_loading=True)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        assert not file_loader.is_streamable
        assert file_loader.file_reader is not None

        lazy_parts = file_loader._load_lazily()
        assert isinstance(lazy_parts, list)
        assert len(lazy_parts) > 1

        # Non-streamable lazy parts use integer indices (pos=None).
        for part in lazy_parts:
            assert isinstance(part, LazyLoadedPartData)
            assert part.pos is None

        # Collection opened a handle for the count read; _loaded_data is not cached yet.
        assert len(file_loader._file_handles) == 1
        assert file_loader._loaded_data is None

        # First resolve: _loaded_data is populated (handle reused, no new open).
        lazy_parts[0].resolve()
        assert file_loader._loaded_data is not None
        cached_id = id(file_loader._loaded_data)  # type: ignore[unreachable]

        # Subsequent resolves reuse _loaded_data without re-reading the file.
        lazy_parts[1].resolve()
        assert id(file_loader._loaded_data) == cached_id

        file_loader.clear_cache()

    def test_content_cache_shared_across_loaders_for_same_file(self) -> None:
        """Test that the session content cache serves the second FileLoader from memory without re-reading disk.

        Two FileLoader instances for the same path backed by the same SessionFileCache should
        trigger only one actual file read: the first loader populates the content cache, and the
        second receives the cached content without touching disk.
        """
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE
        shared_cache = SessionFileCache()
        load_attrs = self._make_load_attrs(load, PATH_TEXT_FILE, lazy_loading=True)
        loader1 = FileLoader(abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, file_cache=shared_cache)
        loader2 = FileLoader(abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, file_cache=shared_cache)

        on_miss_count = 0
        original_get_content = shared_cache.get_content

        def tracking_get_content(key: CacheKey, on_miss: Callable[[], str | bytes]) -> str | bytes:
            def counting_on_miss() -> str | bytes:
                nonlocal on_miss_count
                on_miss_count += 1
                return on_miss()

            return original_get_content(key, counting_on_miss)

        lazy1 = loader1._load_lazily()
        lazy2 = loader2._load_lazily()
        assert isinstance(lazy1, LazyLoadedData)
        assert isinstance(lazy2, LazyLoadedData)

        with patch.object(shared_cache, "get_content", side_effect=tracking_get_content):
            lazy1.resolve()
            lazy2.resolve()

        assert on_miss_count == 1, (
            f"Expected exactly one disk read for two loaders targeting the same file; got {on_miss_count}. "
            "The second loader should be served from the session content cache."
        )
        assert loader1._loaded_data is not None and loader2._loaded_data is not None
        assert loader1._loaded_data.data == loader2._loaded_data.data

    def test_weakref_finalize_clears_cache_on_gc(self) -> None:
        """Test that GC-ing a FileLoader triggers the weakref finalizer, closing cached file handles"""
        abs_file_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_ARRAY
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_ARRAY, lazy_loading=False)
        file_loader = FileLoader(
            abs_file_path, load_attrs, load_from=ABS_PATH_LOADER_DIR, strip_trailing_whitespace=True
        )
        file_loader.load()

        # Eager loading with file_reader caches an open file handle
        assert len(file_loader._file_handles) == 1
        f_handle = file_loader._file_handles[0]
        assert not f_handle.closed

        # Capture a reference to the file handles list before deleting the loader
        file_handles = file_loader._file_handles

        del file_loader
        gc.collect()

        # Finalizer should have closed the file handle and cleared the file handles list
        assert f_handle.closed
        assert file_handles == []


class TestFileLoaderWithCompressedFiles:
    """Tests for compression-aware file loading (.gz/.bz2/.xz)."""

    def _make_load_attrs(self, loader: DataLoader, path: Path, *, lazy_loading: bool = False) -> DataLoaderLoadAttrs:
        """Create minimal DataLoaderLoadAttrs for the given loader and path.

        :param loader: The data loader to use
        :param path: Relative path to the test data file
        :param lazy_loading: Whether to use lazy loading
        """
        return DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(__file__),
            fixture_names=("file_path", "data"),
            path=path,
            lazy_loading=lazy_loading,
        )

    def test_get_effective_suffix_returns_inner_suffix_for_compressed_paths(self) -> None:
        """Test that get_effective_suffix strips the compression suffix to expose the inner format suffix"""
        assert get_effective_suffix(Path("data.json.gz")) == ".json"
        assert get_effective_suffix(Path("data.csv.bz2")) == ".csv"
        assert get_effective_suffix(Path("data.txt.xz")) == ".txt"
        assert get_effective_suffix(Path("data.JSON.GZ")) == ".JSON"

    def test_get_effective_suffix_returns_suffix_for_non_compressed_paths(self) -> None:
        """Test that get_effective_suffix is a no-op for non-compressed paths"""
        assert get_effective_suffix(Path("data.json")) == ".json"
        assert get_effective_suffix(Path("data.txt")) == ".txt"

    def test_get_effective_suffix_returns_gz_when_no_inner_suffix(self) -> None:
        """Test that get_effective_suffix returns the compression suffix itself when there is no inner suffix"""
        assert get_effective_suffix(Path("data.gz")) == ".gz"
        assert get_effective_suffix(Path("data.bz2")) == ".bz2"
        assert get_effective_suffix(Path("data.xz")) == ".xz"

    def test_compression_aware_open_routes_gz_through_gzip(self, tmp_path: Path) -> None:
        """Test that compression_aware_open opens .gz files via gzip and returns decompressed text"""
        payload = "hello compressed world\n"
        gz_path = tmp_path / "test.txt.gz"
        with gzip.open(gz_path, "wt") as f:
            f.write(payload)

        with compression_aware_open(gz_path) as f:
            assert f.read() == payload

    def test_compressed_json_resolves_to_default_json_reader(self) -> None:
        """Test that FileLoader for a .json.gz file resolves to the default json.load reader"""
        abs_path = ABS_PATH_LOADER_DIR / PATH_JSON_FILE_GZ
        load_attrs = self._make_load_attrs(load, PATH_JSON_FILE_GZ)
        file_loader = FileLoader(abs_path, load_attrs, load_from=ABS_PATH_LOADER_DIR)

        assert file_loader.file_reader is json.load

    def test_compressed_file_disables_streaming(self) -> None:
        """Test that FileLoader marks compressed files as non-streamable to avoid O(n) seeks"""
        abs_path = ABS_PATH_LOADER_DIR / PATH_TEXT_FILE_GZ
        load_attrs = self._make_load_attrs(parametrize, PATH_TEXT_FILE_GZ)
        file_loader = FileLoader(abs_path, load_attrs, load_from=ABS_PATH_LOADER_DIR)

        assert not file_loader.is_streamable

    def test_compressed_binary_autodetect_via_decompressed_chunk(self, tmp_path: Path) -> None:
        """Test that binary auto-detection probes decompressed bytes, not the gzip magic bytes"""
        binary_payload = bytes(range(256))
        gz_path = tmp_path / "binary.dat.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(binary_payload)

        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=gz_path,
            lazy_loading=False,
        )
        file_loader = FileLoader(gz_path, load_attrs)
        loaded = file_loader.load()

        assert isinstance(loaded, LoadedData)
        assert loaded.data == binary_payload
        assert file_loader.read_mode == "rb"

    def test_compressed_text_autodetect_via_decompressed_chunk(self, tmp_path: Path) -> None:
        """Test that text auto-detection probes decompressed bytes and resolves to text mode"""
        text_payload = "hello from compressed text\n"
        gz_path = tmp_path / "text.dat.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write(text_payload)

        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=gz_path,
            lazy_loading=False,
        )
        file_loader = FileLoader(gz_path, load_attrs)
        loaded = file_loader.load()

        assert isinstance(loaded, LoadedData)
        assert loaded.data == text_payload
        assert file_loader.read_mode == "r"

    @pytest.mark.parametrize("ext", [x.upper() for x in SUPPORTED_COMPRESSION_EXTENSIONS])
    def test_compressed_uppercase_suffix_is_routed(self, tmp_path: Path, ext: str) -> None:
        """Test that uppercase compression suffixes are routed the same as lowercase"""
        payload = "case insensitive\n"
        path = tmp_path / f"data.txt{ext}"
        with compression_aware_open(path, mode="wt") as f:
            f.write(payload)
        load_attrs = DataLoaderLoadAttrs(
            loader=load,
            search_from=Path(__file__),
            fixture_names=("data",),
            path=path,
            lazy_loading=False,
        )
        file_loader = FileLoader(path, load_attrs)
        loaded = file_loader.load()
        assert isinstance(loaded, LoadedData)
        assert loaded.data == payload
