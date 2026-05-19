from __future__ import annotations

import logging
import sys
from collections import OrderedDict
from collections.abc import Callable
from typing import IO, Any, Literal

from pytest_data_loader.constants import DEFAULT_MAX_CACHED_CONTENT_BYTES, DEFAULT_MAX_OPEN_FILE_HANDLES
from pytest_data_loader.types import HashableDict

logger = logging.getLogger(__name__)

# (abs_path, mtime_ns, file_size, read_options)
CacheKey = tuple[str, int, int, HashableDict]
# (abs_path, mtime_ns, file_size, effective_encoding)
ReadModeKey = tuple[str, int, int, str]


class SessionFileCache:
    """Session-scoped cache shared across all FileLoader instances within a pytest session.

    Provides three complementary caches that sit *below* any user transform chain:

    **Raw-content LRU** — caches the str/bytes returned by file reads. mtime_ns and file_size in the key make entries
    self-invalidating when a file changes during a run. Using the full read_options (not just encoding) ensures
    loaders with different errors or newline parameters never share a cache entry.  Only plain _read_file() reads
    are cached. file_reader output and all user transform results are excluded because those callables may be
    non-idempotent or return generators.

    **Bounded handle pool** — keeps at most MAX_OPEN_FILE_HANDLES open file handles, evicting (and closing) the
    least-recently-used handle when the pool is full.  Keyed by (abs_path, mtime_ns, file_size, read_options) —
    the same fields as the content key — so a file changed mid-run maps to a new handle key and the stale FD is evicted
    automatically.  Each access re-fetches via get_handle() and seeks to the required position, so eviction between
    accesses is safe (the handle is simply reopened on next access).  Set max_open_handles=0 to disable pooling.
    FileLoader will fall back to its per-instance handle instead (check pooling_enabled before calling get_handle).

    **Read-mode memo** — caches the detected "r"/"rb" result of the binary-probe open. Eliminates redundant 4 KiB
    probe opens when multiple FileLoader instances target the same file with the same encoding in the same session.

    Invalidation note: cache keys include mtime_ns and file_size captured when a FileLoader is constructed, so entries
    are self-invalidating across new loader instances if a file changes between test runs. Within a single reused
    FileLoader (same parametrized test function, multiple cases) the stat is frozen at first access; mid-session
    file mutations are not detected for that loader's lifetime.

    NOTE: None of the three caches is thread-safe. Under pytest-xdist each worker is a separate process with its own
          SessionFileCache instance. The configured byte cap therefore applies per worker, not globally.
    """

    def __init__(
        self,
        max_content_bytes: int = DEFAULT_MAX_CACHED_CONTENT_BYTES,
        max_open_handles: int = DEFAULT_MAX_OPEN_FILE_HANDLES,
    ) -> None:
        """Initialize the session file cache.

        :param max_content_bytes: Cumulative byte cap for the raw-content LRU cache.
        :param max_open_handles: Maximum number of simultaneously open pooled file handles.
        """
        self._max_content_bytes = max_content_bytes
        self._max_open_handles = max_open_handles
        # (content, measured byte size) ordered oldest → newest
        self._content: OrderedDict[CacheKey, tuple[str | bytes, int]] = OrderedDict()
        self._content_bytes: int = 0
        # open handles ordered oldest → newest
        self._handles: OrderedDict[CacheKey, IO[Any]] = OrderedDict()
        # detected read mode ("r" or "rb") keyed by (abs_path, mtime_ns, file_size, encoding).
        # Intentionally unbounded: keys are O(bytes) tiny and the number of distinct (file, encoding)
        # pairs in a session is bounded by the test suite itself.
        self._read_modes: dict[ReadModeKey, Literal["r", "rb"]] = {}

    @property
    def pooling_enabled(self) -> bool:
        """Return True when handle pooling is active (max_open_handles > 0)."""
        return self._max_open_handles > 0

    def get_content(self, key: CacheKey, on_miss: Callable[[], str | bytes]) -> str | bytes:
        """Return cached raw file content, calling on_miss on a cache miss.

        The result is stored only if its measured size does not exceed max_content_bytes alone
        (a single file larger than the cap is returned uncached to avoid evict-thrash).
        Size is len(data) for binary content and sys.getsizeof(data) for text.

        :param key: Cache key
        :param on_miss: Zero-argument callable that reads and returns the raw file content.
        """
        if key in self._content:
            self._content.move_to_end(key)
            return self._content[key][0]

        data = on_miss()
        # len() for bytes gives exact payload size; sys.getsizeof() for str is an approximation
        # (includes interpreter overhead, varies with code-point width) — deliberate: exact for
        # binary, close-enough for text, consistent cap enforcement across both.
        byte_size = len(data) if isinstance(data, (bytes, bytearray)) else sys.getsizeof(data)
        if byte_size <= self._max_content_bytes:
            while self._content and self._content_bytes + byte_size > self._max_content_bytes:
                _, (_, evicted_size) = self._content.popitem(last=False)
                self._content_bytes -= evicted_size
            self._content[key] = (data, byte_size)
            self._content_bytes += byte_size
        return data

    def get_handle(self, key: CacheKey, on_miss: Callable[[], IO[Any]]) -> IO[Any]:
        """Return a pooled open file handle, opening it via opener when missing or closed.

        When the pool is at capacity the least-recently-used handle is closed and removed
        before inserting the new one.  Callers must seek to the desired position after
        receiving the handle.

        When max_open_handles is 0 (pooling disabled) the handle is opened via on_miss and
        returned directly without touching the pool.

        :param key: Cache key
        :param on_miss: Zero-argument callable that opens and returns a new file handle.
        """
        if self._max_open_handles == 0:
            return on_miss()

        f = self._handles.get(key)
        if f is not None and not f.closed:
            self._handles.move_to_end(key)
            return f

        if key in self._handles:
            del self._handles[key]

        # New handle opened before evicting the LRU — pool briefly holds max+1 fds.
        f = on_miss()
        if len(self._handles) >= self._max_open_handles:
            _, lru = self._handles.popitem(last=False)
            try:
                lru.close()
            except Exception:
                logger.exception("Failed to close evicted file handle")
        self._handles[key] = f
        return f

    def get_read_mode(self, key: ReadModeKey, on_miss: Callable[[], Literal["r", "rb"]]) -> Literal["r", "rb"]:
        """Return the cached detected read mode ("r" or "rb"), probing on a miss.

        Eliminates redundant binary-probe opens across FileLoader instances that target the same file and encoding
        within a session.

        :param key: Cache key
        :param on_miss: Zero-argument callable that runs the binary probe and returns "r" or "rb".
        """
        if key not in self._read_modes:
            self._read_modes[key] = on_miss()
        return self._read_modes[key]

    def clear(self) -> None:
        """Close all pooled handles and drop all cached content and memos. Idempotent."""
        for f in self._handles.values():
            try:
                f.close()
            except Exception:
                logger.exception("Failed to close pooled file handle during cache clear")
        self._handles.clear()
        self._content.clear()
        self._content_bytes = 0
        self._read_modes.clear()
