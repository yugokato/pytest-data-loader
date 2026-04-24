import sys
from pathlib import Path

import pytest
from pytest import FixtureRequest

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.paths import resolve_relative_path
from tests.paths import (
    ABS_PATH_LOADER_DIR,
    PATH_HIDDEN_DIR,
    PATH_HIDDEN_FILE,
    PATH_JSON_FILE_OBJECT,
    PATH_TEXT_FILE,
    SOME_DIR,
    SOME_DIR_INNER,
    SYMLINK_DIR,
)

pytestmark = pytest.mark.unittest


SEARCH_FROM = Path(__file__)
LOCAL_LOADER_DIR = SEARCH_FROM.resolve().parent / DEFAULT_LOADER_DIR_NAME
MARK_PY310_GLOBSTAR_BUG = pytest.mark.xfail(
    # Python 3.10 falsely matches files named 'xyz' with glob pattern 'xyz/**'
    condition=sys.version_info < (3, 11),
    reason="https://github.com/python/cpython/pull/115291",
)


class TestPathResolver:
    """Tests for the relative path resolver."""

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_should_find_from_nearest_data_dir(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that the relative path specified is located from the nearest data directory if the same path exists
        under multiple data directories
        """
        assert (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).exists()
        assert (LOCAL_LOADER_DIR / PATH_TEXT_FILE).exists()
        if is_file:
            path = PATH_TEXT_FILE
        else:
            path = PATH_TEXT_FILE.parent
        data_dir_path, (resolved_path,) = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, path, SEARCH_FROM, is_file=is_file
        )
        if is_file:
            assert data_dir_path == resolved_path.parent.parent.parent == LOCAL_LOADER_DIR
        else:
            assert data_dir_path == resolved_path.parent.parent == LOCAL_LOADER_DIR

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_should_find_from_upper_data_dir(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that the relative path specified is located from an upper-level data directory if one doesn't exist in
        the lower-level data directory
        """
        assert (ABS_PATH_LOADER_DIR / PATH_JSON_FILE_OBJECT).exists()
        assert not (LOCAL_LOADER_DIR / PATH_JSON_FILE_OBJECT).exists()
        if is_file:
            path = PATH_JSON_FILE_OBJECT
        else:
            path = PATH_JSON_FILE_OBJECT.parent
        data_dir_path, (resolved_path,) = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, path, SEARCH_FROM, is_file=is_file
        )
        if is_file:
            assert data_dir_path == resolved_path.parent.parent.parent == ABS_PATH_LOADER_DIR
        else:
            assert data_dir_path == resolved_path.parent.parent == ABS_PATH_LOADER_DIR

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_should_find_hidden_item(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that relative path for a hidden file or directory should be found"""
        if is_file:
            path = PATH_HIDDEN_FILE
        else:
            path = PATH_HIDDEN_DIR
        data_dir_path, (resolved_path,) = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, path, SEARCH_FROM, is_file=is_file
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_path.name == path.name

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_should_not_follow_symlinks(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that relative path for a symlink should be found as is (Symlinks is resolved by OS)"""
        if is_file:
            path = Path(SYMLINK_DIR, "symlink.txt")
        else:
            path = Path(SYMLINK_DIR, "dir", "symlink")
        data_dir_path, (resolved_path,) = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME,
            request.config.rootpath,
            path,
            SEARCH_FROM,
            is_file=is_file,
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_path.is_symlink()
        assert resolved_path == (ABS_PATH_LOADER_DIR / path)

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_should_ignore_unmatched_path_type(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that relative path for an unmatched path type should be ignored when the relative path is identical"""
        assert (ABS_PATH_LOADER_DIR / SOME_DIR).exists()
        assert (ABS_PATH_LOADER_DIR / SOME_DIR).is_dir()
        assert (LOCAL_LOADER_DIR / SOME_DIR).exists()
        assert (LOCAL_LOADER_DIR / SOME_DIR).is_file()

        data_dir_path, (resolved_path,) = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(SOME_DIR), SEARCH_FROM, is_file=is_file
        )
        if is_file:
            assert data_dir_path == resolved_path.parent == LOCAL_LOADER_DIR
        else:
            assert data_dir_path == resolved_path.parent == ABS_PATH_LOADER_DIR

    @pytest.mark.parametrize("is_file", [True, False])
    @pytest.mark.parametrize("is_valid_data_dir", [True, False])
    def test_path_resolver_should_raise_error_if_not_found(
        self, request: FixtureRequest, is_valid_data_dir: bool, is_file: bool
    ) -> None:
        """Test that non-existing path should be handled as FileNotFoundError error"""
        non_existing_path = Path("foo")
        if is_file:
            non_existing_path /= "bar.txt"

        data_dir_path = DEFAULT_LOADER_DIR_NAME if is_valid_data_dir else "invalid_dir"
        with pytest.raises(FileNotFoundError):
            resolve_relative_path(
                data_dir_path, request.config.rootpath, non_existing_path, SEARCH_FROM, is_file=is_file
            )

    def test_path_resolver_should_raise_error_with_symlink_eloop(self, request: FixtureRequest) -> None:
        """Test that a circular symlink (ELOOP) should be detected

        NOTE: A loop caused by directory traversal cycles won't be detected with non glob pattern paths at this timing.
              It will be checked later when recursively collecting dir files
        """
        with pytest.raises(RuntimeError, match="Detected a circular symlink"):
            resolve_relative_path(
                DEFAULT_LOADER_DIR_NAME,
                request.config.rootpath,
                Path(SYMLINK_DIR, "circular", "symlink.txt"),
                SEARCH_FROM,
                is_file=True,
            )


class TestPathResolverGlob:
    """Tests for the relative path resolver with glob patterns."""

    _DIR_TXT_NAMES = ("0.txt", "1.txt", "2.txt")
    _DIR_INNER_TXT_NAMES = ("3.txt", "4.txt", "5.txt")

    SUB_DIR = ABS_PATH_LOADER_DIR / SOME_DIR

    def test_path_resolver_glob_should_resolve_single_wildcard(self, request: FixtureRequest) -> None:
        """Test that a single-wildcard pattern resolves to all matching files in the nearest data directory containing
        matches.
        """
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME,
            request.config.rootpath,
            Path(f"{SOME_DIR}/*.txt"),
            SEARCH_FROM,
            is_file=True,
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_paths == tuple(self.SUB_DIR / n for n in self._DIR_TXT_NAMES)
        assert all(p.is_file() for p in resolved_paths)

    @pytest.mark.parametrize("is_file", [pytest.param(True, marks=MARK_PY310_GLOBSTAR_BUG), False])
    def test_path_resolver_glob_should_resolve_globstar(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that a recursive `**` pattern matches files or directories at all depths under the data directory."""
        pattern = f"{SOME_DIR}/**"
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(pattern), SEARCH_FROM, is_file=is_file
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        if is_file:
            expected = tuple(
                sorted(
                    [self.SUB_DIR / n for n in self._DIR_TXT_NAMES]
                    + [self.SUB_DIR / SOME_DIR_INNER / n for n in self._DIR_INNER_TXT_NAMES]
                )
            )
        else:
            expected = tuple(sorted((self.SUB_DIR, self.SUB_DIR / SOME_DIR_INNER)))
        assert resolved_paths == expected

    def test_path_resolver_glob_should_resolve_character_class(self, request: FixtureRequest) -> None:
        """Test that a `[...]` character-class pattern matches only the listed characters."""
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME,
            request.config.rootpath,
            Path(f"{SOME_DIR}/[01].txt"),
            SEARCH_FROM,
            is_file=True,
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_paths == (self.SUB_DIR / "0.txt", self.SUB_DIR / "1.txt")

    def test_path_resolver_glob_should_find_from_nearest_data_dir(self, request: FixtureRequest) -> None:
        """Test that when the pattern matches in multiple data directories, the nearest one wins."""
        assert (ABS_PATH_LOADER_DIR / PATH_TEXT_FILE).exists()
        assert (LOCAL_LOADER_DIR / PATH_TEXT_FILE).exists()
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path("files/text/*.txt"), SEARCH_FROM, is_file=True
        )
        assert data_dir_path == LOCAL_LOADER_DIR
        assert resolved_paths == (LOCAL_LOADER_DIR / PATH_TEXT_FILE,)

    def test_path_resolver_glob_should_find_from_upper_data_dir(self, request: FixtureRequest) -> None:
        """Test that the search proceeds to an upper data directory when the nearest one yields no glob matches."""
        assert (LOCAL_LOADER_DIR / SOME_DIR).is_file()
        assert self.SUB_DIR.is_dir()
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME,
            request.config.rootpath,
            Path(f"{SOME_DIR}/*.txt"),
            SEARCH_FROM,
            is_file=True,
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_paths == tuple(self.SUB_DIR / n for n in self._DIR_TXT_NAMES)

    @pytest.mark.parametrize("is_file", [pytest.param(True, marks=MARK_PY310_GLOBSTAR_BUG), False])
    def test_path_resolver_glob_should_exclude_hidden_items(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that wildcard expansion excludes hidden files."""
        assert (ABS_PATH_LOADER_DIR / PATH_HIDDEN_FILE).exists()
        assert (ABS_PATH_LOADER_DIR / PATH_HIDDEN_DIR).exists()
        data_dir_path, resolved_paths = resolve_relative_path(
            DEFAULT_LOADER_DIR_NAME, request.config.rootpath, Path(f"{SOME_DIR}/**"), SEARCH_FROM, is_file=is_file
        )
        assert data_dir_path == ABS_PATH_LOADER_DIR
        assert resolved_paths
        assert all(not p.name.startswith(".") for p in resolved_paths)

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_glob_should_raise_when_no_matches(self, request: FixtureRequest, is_file: bool) -> None:
        """Test that an unmatched glob pattern raises FileNotFoundError with a message naming the pattern and searched
        data dirs.
        """
        expected_kind = "files" if is_file else "directories"
        with pytest.raises(
            FileNotFoundError,
            match=f"matched no {expected_kind} under any of the following data directories",
        ):
            resolve_relative_path(
                DEFAULT_LOADER_DIR_NAME,
                request.config.rootpath,
                Path(f"{SOME_DIR}/*.nonexistent"),
                SEARCH_FROM,
                is_file=is_file,
            )

    @pytest.mark.parametrize("is_file", [True, False])
    def test_path_resolver_glob_should_raise_error_on_circular_symlink(
        self, request: FixtureRequest, is_file: bool
    ) -> None:
        """Test that a circular symlink (both ELOOP and directory traversal cycles) should be detected"""
        circular_dir = Path(SYMLINK_DIR, "circular")
        if is_file:
            path = circular_dir / "*.txt"
        else:
            path = circular_dir / "dir/**"
        with pytest.raises(RuntimeError, match="Detected a circular symlink"):
            resolve_relative_path(
                DEFAULT_LOADER_DIR_NAME,
                request.config.rootpath,
                path,
                SEARCH_FROM,
                is_file=is_file,
            )
