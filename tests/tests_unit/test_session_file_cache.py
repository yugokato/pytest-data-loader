from __future__ import annotations

import sys
from io import StringIO
from typing import Any
from unittest.mock import MagicMock

import pytest

from pytest_data_loader.loaders.cache import CacheKey, ReadModeKey, SessionFileCache
from pytest_data_loader.types import HashableDict

pytestmark = pytest.mark.unittest


def _content_key(
    path: str = "/a/b.txt", mtime: int = 1, size: int = 10, read_options: dict[str, Any] | None = None
) -> CacheKey:
    return (path, mtime, size, HashableDict(read_options or {"mode": "r", "encoding": "utf-8"}))


def _handle_key(
    path: str = "/a/b.txt", mtime: int = 1, size: int = 10, read_options: dict[str, Any] | None = None
) -> CacheKey:
    return (path, mtime, size, HashableDict(read_options or {"mode": "r", "encoding": "utf-8"}))


def _read_mode_key(path: str = "/a/b.txt", mtime: int = 1, size: int = 10, encoding: str = "utf-8") -> ReadModeKey:
    return (path, mtime, size, encoding)


class TestSessionFileCacheGetContent:
    """Tests for SessionFileCache.get_content()"""

    def test_cache_miss_calls_on_miss_and_returns_data(self) -> None:
        """Test that a cache miss calls on_miss() and returns the result."""
        cache = SessionFileCache()
        key = _content_key()
        value = "hello"
        on_miss = MagicMock(return_value=value)
        result = cache.get_content(key, on_miss)
        assert result == value
        on_miss.assert_called_once()

    def test_cache_hit_returns_cached_data_without_calling_on_miss(self) -> None:
        """Test that a cache hit returns the cached value without calling on_miss() again."""
        cache = SessionFileCache()
        key = _content_key()
        value = "hello"
        on_miss = MagicMock(return_value=value)
        cache.get_content(key, on_miss)
        result = cache.get_content(key, on_miss)
        assert result == value
        assert on_miss.call_count == 1

    def test_bytes_content_is_cached_and_returned(self) -> None:
        """Test that bytes content is cached and returned correctly."""
        cache = SessionFileCache()
        key = _content_key(read_options={"mode": "rb"})
        value = b"\x00\x01\x02"
        on_miss = MagicMock(return_value=value)
        result = cache.get_content(key, on_miss)
        assert result == value
        on_miss.reset_mock()
        assert cache.get_content(key, on_miss) == value
        on_miss.assert_not_called()

    def test_different_keys_are_independent(self) -> None:
        """Test that two different keys produce independent cache entries."""
        cache = SessionFileCache()
        key_a = _content_key(path="/a.txt")
        key_b = _content_key(path="/b.txt")
        value_a = "aaa"
        value_b = "bbb"
        on_miss_a = MagicMock(return_value=value_a)
        on_miss_b = MagicMock(return_value=value_b)
        cache.get_content(key_a, on_miss_a)
        cache.get_content(key_b, on_miss_b)
        assert cache.get_content(key_a, MagicMock()) == value_a
        assert cache.get_content(key_b, MagicMock()) == value_b

    def test_mtime_change_causes_cache_miss(self) -> None:
        """Test that changing mtime_ns in the key causes a cache miss."""
        cache = SessionFileCache()
        key_old = _content_key(mtime=100)
        key_new = _content_key(mtime=200)
        value_new = "new"
        on_miss_old = MagicMock(return_value="old")
        on_miss_new = MagicMock(return_value=value_new)
        cache.get_content(key_old, on_miss_old)
        result = cache.get_content(key_new, on_miss_new)
        assert result == value_new
        on_miss_new.assert_called_once()

    def test_size_change_causes_cache_miss(self) -> None:
        """Test that changing file size in the key causes a cache miss."""
        cache = SessionFileCache()
        key_a = _content_key(size=10)
        key_b = _content_key(size=20)
        cache.get_content(key_a, MagicMock(return_value="small"))
        value_b = "large"
        on_miss_b = MagicMock(return_value=value_b)
        result = cache.get_content(key_b, on_miss_b)
        assert result == value_b
        on_miss_b.assert_called_once()

    def test_lru_eviction_when_cumulative_bytes_exceeded(self) -> None:
        """Test that LRU entries are evicted when the cumulative byte cap is reached."""
        value = "a" * 6
        size = sys.getsizeof(value)
        # Cap fits exactly one entry; adding a second triggers eviction of the first.
        cache = SessionFileCache(max_content_bytes=size)
        key_a = _content_key(path="/a.txt")
        key_b = _content_key(path="/b.txt")
        cache.get_content(key_a, lambda: value)
        cache.get_content(key_b, lambda: value)  # triggers eviction of "a"

        on_miss_a = MagicMock(return_value=value)
        cache.get_content(key_a, on_miss_a)
        on_miss_a.assert_called_once()  # "a" was evicted; must re-read

    def test_lru_order_updated_on_cache_hit(self) -> None:
        """Test that a cache hit moves the entry to MRU so it isn't evicted first."""
        # Cap holds exactly 2 same-size entries; inserting a third evicts the LRU.
        # We verify membership in the internal OrderedDict to avoid re-insertion side effects.
        value = "aaa"
        size = sys.getsizeof(value)
        cache = SessionFileCache(max_content_bytes=size * 2)
        key_a = _content_key(path="/a.txt")
        key_b = _content_key(path="/b.txt")
        key_c = _content_key(path="/c.txt")
        cache.get_content(key_a, lambda: "aaa")  # order: [A]
        cache.get_content(key_b, lambda: "bbb")  # order: [A, B]
        cache.get_content(key_a, MagicMock())  # hit A → promote; order: [B, A]
        cache.get_content(key_c, lambda: "ccc")  # evicts B (LRU); order: [A, C]
        assert key_b not in cache._content  # B (LRU) was evicted
        assert key_a in cache._content  # A (MRU-promoted) survived

    def test_max_content_bytes_zero_disables_caching(self) -> None:
        """Test that max_content_bytes=0 returns data on every call but never stores it."""
        cache = SessionFileCache(max_content_bytes=0)
        key = _content_key()
        data = "x"
        on_miss = MagicMock(return_value=data)

        result1 = cache.get_content(key, on_miss)
        result2 = cache.get_content(key, on_miss)
        assert result1 == data
        assert result2 == data
        assert on_miss.call_count == 2
        assert cache._content == {}  # never stored anything

    def test_single_file_larger_than_cap_returned_but_not_cached(self) -> None:
        """Test that a file exceeding max_content_bytes is returned uncached."""
        # sys.getsizeof("") > 1, so cap=1 ensures any string exceeds the cap.
        cache = SessionFileCache(max_content_bytes=1)
        key = _content_key()
        data = "x"
        on_miss = MagicMock(return_value=data)
        result = cache.get_content(key, on_miss)
        assert result == data

        on_miss2 = MagicMock(return_value=data)
        cache.get_content(key, on_miss2)
        on_miss2.assert_called_once()  # not cached; must re-read

    def test_different_read_options_produce_independent_entries(self) -> None:
        """Test that keys with the same path/mtime/size but different read_options are independent.

        Regression: the old key used only (mode, encoding), so two loaders with the same
        encoding but different ``errors`` or ``newline`` would collide and the second would
        receive the first loader's content.
        """
        cache = SessionFileCache()
        key_strict = _content_key(read_options={"mode": "r", "encoding": "utf-8", "errors": "strict"})
        key_ignore = _content_key(read_options={"mode": "r", "encoding": "utf-8", "errors": "ignore"})
        cache.get_content(key_strict, MagicMock(return_value="strict content"))
        on_miss_ignore = MagicMock(return_value="ignore content")
        result = cache.get_content(key_ignore, on_miss_ignore)
        assert result == "ignore content"
        on_miss_ignore.assert_called_once()

    def test_content_bytes_tracked_correctly(self) -> None:
        """Test that _content_bytes reflects the total in-memory object size of stored content."""
        cache = SessionFileCache()
        cache.get_content(_content_key(path="/a.txt"), lambda: "hello")
        cache.get_content(_content_key(path="/b.txt"), lambda: "world!")
        assert cache._content_bytes == sys.getsizeof("hello") + sys.getsizeof("world!")

    def test_max_content_bytes_zero_does_not_cache_empty_bytes(self) -> None:
        """Test that max_content_bytes=0 never stores anything, including zero-byte content.

        Regression: len(b"") == 0, so the guard ``byte_size <= max_content_bytes`` was True when
        max_content_bytes=0, causing an empty binary file to be cached despite caching being disabled.
        """
        cache = SessionFileCache(max_content_bytes=0)
        key = _content_key(read_options={"mode": "rb"})
        on_miss = MagicMock(return_value=b"")
        cache.get_content(key, on_miss)
        cache.get_content(key, on_miss)
        assert on_miss.call_count == 2, "on_miss must be called every time when caching is disabled"
        assert cache._content == {}, "Nothing should be stored when max_content_bytes=0"


class TestSessionFileCacheGetHandle:
    """Tests for SessionFileCache.get_handle()"""

    def test_cache_miss_calls_opener_and_returns_handle(self) -> None:
        """Test that a pool miss calls opener() and returns the resulting handle."""
        cache = SessionFileCache()
        handle = StringIO("content")
        opener = MagicMock(return_value=handle)
        result = cache.get_handle(_handle_key(), opener)
        assert result is handle
        opener.assert_called_once()

    def test_cache_hit_returns_same_handle_without_calling_opener(self) -> None:
        """Test that a pool hit returns the same open handle without calling opener() again."""
        cache = SessionFileCache()
        handle = StringIO("content")
        opener = MagicMock(return_value=handle)
        cache.get_handle(_handle_key(), opener)
        result = cache.get_handle(_handle_key(), opener)
        assert result is handle
        assert opener.call_count == 1

    def test_different_keys_produce_independent_handles(self) -> None:
        """Test that two different keys yield independent pool entries."""
        cache = SessionFileCache()
        h1 = StringIO("one")
        h2 = StringIO("two")
        r1 = cache.get_handle(("/a.txt", 1, 10, HashableDict()), lambda: h1)
        r2 = cache.get_handle(("/b.txt", 1, 10, HashableDict()), lambda: h2)
        assert r1 is h1
        assert r2 is h2

    def test_pool_never_exceeds_max_open_handles(self) -> None:
        """Test that the pool never holds more than max_open_handles simultaneously-open handles.

        Regression: the old implementation opened the new handle before evicting the LRU,
        transiently holding max+1 open fds and risking EMFILE near ulimit.
        """
        max_handles = 3
        cache = SessionFileCache(max_open_handles=max_handles)
        open_counts: list[int] = []
        handles: list[StringIO] = []

        def opener(name: str) -> StringIO:
            h = StringIO(name)
            handles.append(h)
            open_counts.append(sum(1 for hh in handles if not hh.closed))
            return h

        for i in range(max_handles + 3):
            cache.get_handle((f"/{i}.txt", 1, 10, HashableDict()), lambda n=str(i): opener(n))

        assert max(open_counts) <= max_handles, (
            f"Pool exceeded max_open_handles={max_handles}: peak was {max(open_counts)}"
        )

    def test_eviction_closes_lru_handle_when_pool_full(self) -> None:
        """Test that LRU handle is closed and removed when pool capacity is exceeded."""
        cache = SessionFileCache(max_open_handles=2)
        h1 = StringIO("one")
        h2 = StringIO("two")
        h3 = StringIO("three")
        cache.get_handle(("/a.txt", 1, 10, HashableDict()), lambda: h1)
        cache.get_handle(("/b.txt", 1, 10, HashableDict()), lambda: h2)
        cache.get_handle(("/c.txt", 1, 10, HashableDict()), lambda: h3)  # evicts h1 (LRU)
        assert h1.closed
        assert not h2.closed
        assert not h3.closed
        assert len(cache._handles) == 2

    def test_lru_order_updated_on_cache_hit_and_evicts_entry(self) -> None:
        """Test that a hit promotes the entry to MRU, protecting it from eviction."""
        cache = SessionFileCache(max_open_handles=2)
        h1 = StringIO("one")
        h2 = StringIO("two")
        h3 = StringIO("three")
        cache.get_handle(("/a.txt", 1, 10, HashableDict()), lambda: h1)
        cache.get_handle(("/b.txt", 1, 10, HashableDict()), lambda: h2)
        cache.get_handle(("/a.txt", 1, 10, HashableDict()), MagicMock(return_value=None))  # promote h1 to MRU
        cache.get_handle(("/c.txt", 1, 10, HashableDict()), lambda: h3)  # should evict h2, not h1
        assert not h1.closed
        assert h2.closed

    def test_reopens_when_pooled_handle_is_closed(self) -> None:
        """Test that a closed pooled handle is replaced with a fresh one via opener()."""
        cache = SessionFileCache()
        key = _handle_key()
        h1 = StringIO("original")
        opener = MagicMock(return_value=h1)
        result = cache.get_handle(key, opener)
        assert result is h1
        h1.close()  # simulate external close

        h2 = StringIO("fresh")
        opener2 = MagicMock(return_value=h2)
        result = cache.get_handle(key, opener2)
        assert result is h2
        opener2.assert_called_once()

    def test_mtime_change_causes_new_handle(self) -> None:
        """Test that a changed mtime in the key treats the file as a different entry.

        Regression for B1: the old HandleKey was (abs_path, read_options) without
        mtime_ns/file_size, so a file rewritten mid-session would keep returning a
        stale FD.  The new key mirrors ContentKey so invalidation is consistent.
        """
        cache = SessionFileCache()
        h_old = StringIO("old content")
        h_new = StringIO("new content")
        key_old = _handle_key(mtime=100)
        key_new = _handle_key(mtime=200)

        cache.get_handle(key_old, lambda: h_old)
        result = cache.get_handle(key_new, lambda: h_new)

        assert result is h_new, "Changed mtime must produce a new pool entry"
        assert not h_new.closed


class TestSessionFileCacheGetReadMode:
    """Tests for SessionFileCache.get_read_mode()"""

    def test_cache_miss_calls_on_miss_and_returns_mode(self) -> None:
        """Test that a cache miss calls on_miss() and returns the detected mode."""
        cache = SessionFileCache()
        on_miss = MagicMock(return_value="r")
        result = cache.get_read_mode(_read_mode_key(), on_miss)
        assert result == "r"
        on_miss.assert_called_once()

    def test_cache_hit_returns_cached_mode_without_calling_on_miss(self) -> None:
        """Test that a memo hit returns the cached mode without probing again."""
        cache = SessionFileCache()
        on_miss = MagicMock(return_value="rb")
        cache.get_read_mode(_read_mode_key(), on_miss)
        result = cache.get_read_mode(_read_mode_key(), on_miss)
        assert result == "rb"
        assert on_miss.call_count == 1

    def test_different_encodings_produce_independent_entries(self) -> None:
        """Test that different encodings map to independent memo entries."""
        cache = SessionFileCache()
        key_utf8 = _read_mode_key(encoding="utf-8")
        key_latin1 = _read_mode_key(encoding="latin-1")
        cache.get_read_mode(key_utf8, lambda: "r")
        on_miss_latin1 = MagicMock(return_value="rb")
        result = cache.get_read_mode(key_latin1, on_miss_latin1)
        assert result == "rb"
        on_miss_latin1.assert_called_once()

    def test_mtime_change_causes_re_probe(self) -> None:
        """Test that a changed mtime triggers a fresh probe."""
        cache = SessionFileCache()
        key_old = _read_mode_key(mtime=100)
        key_new = _read_mode_key(mtime=200)
        cache.get_read_mode(key_old, lambda: "r")
        on_miss_new = MagicMock(return_value="rb")
        result = cache.get_read_mode(key_new, on_miss_new)
        assert result == "rb"
        on_miss_new.assert_called_once()

    def test_clear_drops_read_mode_memo(self) -> None:
        """Test that clear() removes all memoized read modes."""
        cache = SessionFileCache()
        on_miss = MagicMock(return_value="r")
        cache.get_read_mode(_read_mode_key(), on_miss)
        assert len(cache._read_modes) == 1
        cache.clear()
        assert len(cache._read_modes) == 0
        cache.get_read_mode(_read_mode_key(), on_miss)
        assert on_miss.call_count == 2  # re-probed after clear


class TestSessionFileCacheClear:
    """Tests for SessionFileCache.clear()"""

    def test_clear_closes_all_pooled_handles(self) -> None:
        """Test that clear() closes every open handle in the pool."""
        cache = SessionFileCache()
        h1 = StringIO("a")
        h2 = StringIO("b")
        cache.get_handle(("/a.txt", 1, 10, HashableDict()), lambda: h1)
        cache.get_handle(("/b.txt", 1, 10, HashableDict()), lambda: h2)
        cache.clear()
        assert h1.closed
        assert h2.closed

    def test_clear_empties_handle_pool(self) -> None:
        """Test that clear() removes all entries from the handle pool."""
        cache = SessionFileCache()
        cache.get_handle(_handle_key(), lambda: StringIO("x"))
        assert len(cache._handles) == 1
        cache.clear()
        assert len(cache._handles) == 0

    def test_clear_drops_all_content(self) -> None:
        """Test that clear() removes all entries from the content cache."""
        cache = SessionFileCache()
        cache.get_content(_content_key(), lambda: "data")
        assert len(cache._content) == 1
        cache.clear()
        assert len(cache._content) == 0

    def test_clear_resets_content_bytes_to_zero(self) -> None:
        """Test that clear() resets _content_bytes to 0."""
        cache = SessionFileCache()
        cache.get_content(_content_key(), lambda: "data")
        assert cache._content_bytes > 0
        cache.clear()
        assert cache._content_bytes == 0

    def test_clear_is_idempotent(self) -> None:
        """Test that calling clear() twice raises no error."""
        cache = SessionFileCache()
        cache.get_handle(_handle_key(), lambda: StringIO("x"))
        cache.get_content(_content_key(), lambda: "y")
        cache.clear()
        cache.clear()  # should not raise


class TestHashableDictOrderIndependence:
    """Regression tests for B3: HashableDict hash/eq invariant."""

    def test_equal_dicts_different_insertion_order_have_same_hash(self) -> None:
        """Test that HashableDicts with identical content but different insertion order are equal and hash equal.

        Regression: the old __hash__ used tuple(self.items()), which is order-dependent.
        Two logically equal read_options built in different key orders (e.g. mode injected
        before vs. after encoding) would hash differently, causing silent cache misses.
        """
        d1 = HashableDict({"mode": "r", "encoding": "utf-8"})
        d2 = HashableDict({"encoding": "utf-8", "mode": "r"})
        assert d1 == d2, "Equal content must compare equal"
        assert hash(d1) == hash(d2), "Equal HashableDicts must hash identically regardless of insertion order"

    def test_single_entry_in_set_for_order_variants(self) -> None:
        """Test that order-variant HashableDicts with equal content collapse to one set entry."""
        d1 = HashableDict({"a": 1, "b": 2})
        d2 = HashableDict({"b": 2, "a": 1})
        assert len({d1, d2}) == 1

    def test_used_as_cache_key_regardless_of_insertion_order(self) -> None:
        """Test that two order-variant HashableDicts resolve to the same cache entry."""
        cache = SessionFileCache()
        opts_ab = HashableDict({"mode": "r", "encoding": "utf-8"})
        opts_ba = HashableDict({"encoding": "utf-8", "mode": "r"})
        key_ab: CacheKey = ("/f.txt", 1, 10, opts_ab)
        key_ba: CacheKey = ("/f.txt", 1, 10, opts_ba)
        on_miss = MagicMock(return_value="content")
        cache.get_content(key_ab, on_miss)
        cache.get_content(key_ba, on_miss)  # must be a cache hit
        assert on_miss.call_count == 1, "Order-variant keys must resolve to the same cache entry"
