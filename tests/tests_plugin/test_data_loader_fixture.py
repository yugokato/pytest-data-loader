import json
from pathlib import Path
from typing import Any

import pytest
from pytest import ExitCode, Pytester, RunResult

from pytest_data_loader.types import DataLoaderIniOption, DataLoaderOnMissingAction

pytestmark = pytest.mark.plugin

BUILTIN_FIXTURE = "data_loader"
SCOPED_FIXTURE = "scoped_loader"
PROBE_REPORT_PREFIX = "PROBE_REPORT:"
# Conftest source that counts how data loader fixtures use file loaders and the session file cache
PROBE_CONFTEST = f"""
import json

import pytest
from pytest_data_loader import make_data_loader_fixture
from pytest_data_loader.loaders.cache import SessionFileCache
from pytest_data_loader.loaders.impl import FileLoader

report = dict(file_loaders_created=0, session_cache_reads=0, clear_calls=0, clear_calls_after_teardown=[])
original_init = FileLoader.__init__
original_clear_cache = FileLoader.clear_cache
original_get_content = SessionFileCache.get_content


def counting_init(self, *args, **kwargs):
    report["file_loaders_created"] += 1
    original_init(self, *args, **kwargs)


def counting_clear_cache(self):
    report["clear_calls"] += 1
    original_clear_cache(self)


def counting_get_content(self, *args, **kwargs):
    report["session_cache_reads"] += 1
    return original_get_content(self, *args, **kwargs)


FileLoader.__init__ = counting_init
FileLoader.clear_cache = counting_clear_cache
SessionFileCache.get_content = counting_get_content


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    yield
    report["clear_calls_after_teardown"].append(report["clear_calls"])


def pytest_terminal_summary():
    print("{PROBE_REPORT_PREFIX}" + json.dumps(report))


def pytest_unconfigure():
    FileLoader.__init__ = original_init
    FileLoader.clear_cache = original_clear_cache
    SessionFileCache.get_content = original_get_content
"""
# File content written by the probe project and the data expected to be loaded from it
FILE_CONTENTS: dict[str, tuple[str, Any]] = {
    ".txt": ("hello", "hello"),
    ".json": (json.dumps({"key": "value"}), {"key": "value"}),
}


@pytest.fixture
def data_dir(pytester: Pytester) -> Path:
    return pytester.mkdir("data")


def run_scoped_loader_tests(
    pytester: Pytester, scope: str | None, *, file_name: str = "file.json", num_modules: int = 1
) -> dict[str, Any]:
    """Run tests that load the same file with a data loader fixture and return the report from the probe conftest.

    Each test module has a test class with two tests. A class-scoped fixture is torn down per test unless the tests
    share a class.

    :param pytester: The pytester fixture
    :param scope: The scope of a fixture created with `make_data_loader_fixture()`. None uses the built-in fixture
    :param file_name: Name of the data file to load. The extension decides the file content
    :param num_modules: Number of test modules to create
    """
    content, expected = FILE_CONTENTS[Path(file_name).suffix]
    pytester.makefile(Path(file_name).suffix, **{f"data/{Path(file_name).stem}": content})
    conftest = PROBE_CONFTEST
    fixture_name = BUILTIN_FIXTURE
    if scope is not None:
        fixture_name = SCOPED_FIXTURE
        conftest += f"\n{SCOPED_FIXTURE} = make_data_loader_fixture(scope={scope!r})\n"
    pytester.makeconftest(conftest)
    for i in range(num_modules):
        pytester.makepyfile(
            **{
                f"test_module{i}": f"""
                class TestLoad:
                    def test_first(self, {fixture_name}):
                        assert {fixture_name}({file_name!r}) == {expected!r}

                    def test_second(self, {fixture_name}):
                        assert {fixture_name}({file_name!r}) == {expected!r}
                """
            }
        )

    result = pytester.runpytest("-vs")
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=2 * num_modules)
    return get_probe_report(result)


def get_probe_report(result: RunResult) -> dict[str, Any]:
    """Return the report printed by the probe conftest

    :param result: The result of a pytester run that used the probe conftest
    """
    line = next((x for x in result.outlines if x.startswith(PROBE_REPORT_PREFIX)), None)
    assert line is not None, f"{PROBE_REPORT_PREFIX} not found in output:\n{result.stdout.str()}"
    report: dict[str, Any] = json.loads(line[len(PROBE_REPORT_PREFIX) :])
    return report


class TestDataLoaderFixture:
    """Tests for the data_loader fixture."""

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_load_data(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that data_loader loads a file."""
        abs_path = data_dir / "file.txt"
        abs_path.write_text("hello world")
        path = abs_path if is_abs else abs_path.name

        pytester.makepyfile(f"""
        from pathlib import Path
        def test_load(data_loader):
            data = data_loader(Path({str(path)!r}))
            assert data == "hello world"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_with_reader(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader passes reader to the underlying FileLoader."""
        (data_dir / "file.json").write_text(json.dumps({"k": "v"}))

        pytester.makepyfile("""
        import json

        def test_load(data_loader):
            data = data_loader("file.json", reader=json.load)
            assert data == {"k": "v"}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_with_onload(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader applies the onload function to the loaded data."""
        (data_dir / "file.txt").write_text("hello")

        pytester.makepyfile("""
        def test_load(data_loader):
            data = data_loader("file.txt", onload=lambda d: d.upper())
            assert data == "HELLO"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_with_read_option(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader loads a file with specified read option."""
        data = "test"
        (data_dir / "file.bin").write_text(data)

        pytester.makepyfile(f"""
        def test_load(data_loader):
            data = data_loader("file.bin", read_options={{"mode": "rb"}})
            assert data == b"{data}"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    @pytest.mark.parametrize("invalid_value", ["not-a-dict", [1, 2], 123], ids=["str", "list", "int"])
    def test_load_with_invalid_read_options_type(self, pytester: Pytester, data_dir: Path, invalid_value: str) -> None:
        """Test that passing a non-dict value to read_options raises a clear TypeError."""
        (data_dir / "file.txt").write_text("hello")

        pytester.makepyfile(f"""
        import pytest

        def test_load(data_loader):
            with pytest.raises(TypeError, match="read_options: Must be a dict, but got"):
                data_loader("file.txt", read_options={invalid_value!r})
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_custom_data_dir_name(self, pytester: Pytester) -> None:
        """Test that data_loader respects the data_loader_dir_name INI option."""
        fixtures_dir = pytester.mkdir("fixtures")
        (fixtures_dir / "file.txt").write_text("custom dir")

        pytester.makeini("""
        [pytest]
        data_loader_dir_name = fixtures
        """)
        pytester.makepyfile("""
        def test_load(data_loader):
            data = data_loader("file.txt")
            assert data == "custom dir"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_coexistence_with_load_decorator(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader works alongside a @load decorator on the same test."""
        (data_dir / "static.txt").write_text("static")
        (data_dir / "dynamic.txt").write_text("dynamic")

        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("static_data", "static.txt")
        def test_combined(static_data, data_loader):
            dynamic_data = data_loader("dynamic.txt")
            assert static_data == "static"
            assert dynamic_data == "dynamic"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_class_based_test(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader works inside a class-based test."""
        (data_dir / "file.txt").write_text("in class")

        pytester.makepyfile("""
        class TestSomething:
            def test_load(self, data_loader):
                data = data_loader("file.txt")
                assert data == "in class"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_multiple_calls_same_file(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that repeated calls with the same path return cached data without creating a new FileLoader."""
        (data_dir / "file.txt").write_text("hello")

        # pytester runs in a subprocess, so this global patch is safely isolated.
        pytester.makeconftest("""
        import json
        from pytest_data_loader.loaders.impl import FileLoader

        _loader_count = 0
        _original_init = FileLoader.__init__

        def _counting_init(self, *args, **kwargs):
            global _loader_count
            _loader_count += 1
            _original_init(self, *args, **kwargs)

        FileLoader.__init__ = _counting_init

        def pytest_terminal_summary():
            FileLoader.__init__ = _original_init
            print("LOADER_COUNT:" + json.dumps({"count": _loader_count}))
        """)
        pytester.makepyfile("""
        def test_multi_call(data_loader):
            a = data_loader("file.txt")
            b = data_loader("file.txt")
            assert a == b == "hello"
        """)
        result = pytester.runpytest("-vs")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

        report_prefix = "LOADER_COUNT:"
        report_line = next((line for line in result.outlines if line.startswith(report_prefix)), None)
        assert report_line is not None
        report = json.loads(report_line[len(report_prefix) :])
        assert report["count"] == 1  # memoization: second call hits the cache, no new FileLoader created

    def test_load_nonexistent_relative_path_raises(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader raises for a relative path that cannot be resolved."""
        pytester.makepyfile("""
        import pytest

        def test_load(data_loader):
            with pytest.raises(FileNotFoundError):
                data_loader("does_not_exist.txt")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_nonexistent_absolute_path_raises(self, pytester: Pytester) -> None:
        """Test that data_loader raises FileNotFoundError for an absolute path that does not exist."""
        pytester.makepyfile("""
        import pytest
        from pathlib import Path

        def test_load(data_loader):
            with pytest.raises(FileNotFoundError, match="does not exist"):
                root = Path(".").resolve().anchor
                data_loader(Path(root) / "nonexistent" / "path" / "file.txt")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_directory_path_raises(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader raises ValueError when given a directory path instead of a file."""
        pytester.makepyfile(f"""
        import pytest
        from pathlib import Path

        def test_load(data_loader):
            with pytest.raises(ValueError, match=r"@load .* file path"):
                data_loader(Path({str(data_dir)!r}))
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_with_registered_reader(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader respects file readers registered via register_reader."""
        (data_dir / "file.yaml").write_text("key: value")

        pytester.makeconftest("""
        import yaml
        from pytest_data_loader import register_reader

        register_reader(".yaml", yaml.safe_load)
        """)
        pytester.makepyfile("""
        def test_load(data_loader):
            data = data_loader("file.yaml")
            assert data == {"key": "value"}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)


class TestOnMissingWithFixture:
    """Tests for the data_loader_on_missing INI option behavior with the data_loader fixture."""

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("on_missing", DataLoaderOnMissingAction)
    def test_on_missing(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, on_missing: DataLoaderOnMissingAction
    ) -> None:
        """Test that on_missing governs data_loader fixture behavior for a missing path."""
        path = "does_not_exist.txt"
        if is_abs:
            path = str(data_dir / path)
        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        pytester.makepyfile(f"""
        def test_load(data_loader):
            data_loader({path!r})
        """)
        result = pytester.runpytest("-v")
        if on_missing == DataLoaderOnMissingAction.RAISE:
            assert result.ret == ExitCode.TESTS_FAILED
            result.assert_outcomes(failed=1)
        elif on_missing == DataLoaderOnMissingAction.WARN:
            # warn: data_loader() returns None; test body doesn't use the result, so it passes
            assert result.ret == ExitCode.OK
            result.assert_outcomes(passed=1)
        else:
            assert result.ret == ExitCode.OK
            if on_missing == DataLoaderOnMissingAction.SKIP:
                result.assert_outcomes(skipped=1)
            else:
                result.assert_outcomes(xfailed=1)

        if on_missing == DataLoaderOnMissingAction.WARN:
            result.stdout.fnmatch_lines(
                [
                    "*UserWarning: DataNotFound:*",
                    f"*data_loader({path!r})",
                ],
            )
        else:
            assert "UserWarning: DataNotFound:" not in str(result.stdout)

    def test_jsonl_repeated_call_returns_fresh_generator(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that calling data_loader twice for the same JSONL file yields a fresh iterator each time.

        The DataLoaderFixture._cache must not store a one-shot generator: the second call would return
        the already-exhausted object and list(data) would be empty.
        """
        (data_dir / "file.jsonl").write_text('{"k": 1}\n{"k": 2}\n')

        pytester.makepyfile("""
        def test_load(data_loader):
            data1 = data_loader("file.jsonl")
            items1 = list(data1)
            data2 = data_loader("file.jsonl")  # must not be the same exhausted generator
            items2 = list(data2)
            assert items1 == [{"k": 1}, {"k": 2}], f"First call: {items1!r}"
            assert items2 == [{"k": 1}, {"k": 2}], f"Second call: {items2!r}"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_on_missing_warn_no_duplicate_warning(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that calling data_loader twice for the same missing path emits only one warning."""
        path = str(data_dir / "does_not_exist.txt")
        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {DataLoaderOnMissingAction.WARN.value}
        """)
        pytester.makepyfile(f"""
        def test_load(data_loader):
            data_loader({path!r})
            data_loader({path!r})
        """)
        result = pytester.runpytest("-v", "-W", "always")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)
        assert str(result.stdout).count("UserWarning: DataNotFound:") == 1


class TestDataLoaderFixtureScope:
    """Tests for the built-in data_loader fixture and fixtures created with make_data_loader_fixture()."""

    @pytest.mark.parametrize("scope", ["function", "class", "module", "package", "session"])
    def test_loader_usable_from_fixture_with_same_scope(self, pytester: Pytester, data_dir: Path, scope: str) -> None:
        """Test that a data loader fixture of any scope can be requested from a fixture with the same scope."""
        (data_dir / "config.json").write_text(json.dumps({"key": "value"}))
        pytester.makeconftest(f"""
        import pytest
        from pytest_data_loader import make_data_loader_fixture

        {SCOPED_FIXTURE} = make_data_loader_fixture(scope={scope!r})

        @pytest.fixture(scope={scope!r})
        def loaded_config({SCOPED_FIXTURE}):
            return {SCOPED_FIXTURE}("config.json")
        """)
        pytester.makepyfile("""
        def test_config(loaded_config):
            assert loaded_config == {"key": "value"}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    @pytest.mark.parametrize(
        ("scope", "expected_counts"),
        [
            (None, [1, 2]),
            ("function", [1, 2]),
            ("class", [0, 1]),
            ("module", [0, 1]),
            ("package", [0, 1]),
            ("session", [0, 1]),
        ],
    )
    def test_file_loaders_cleared_at_fixture_teardown(
        self, pytester: Pytester, scope: str | None, expected_counts: list[int]
    ) -> None:
        """Test that file loaders created by a data loader fixture are cleared when the fixture is torn down.

        The expected counts are the number of clear_cache() calls recorded after the teardown of each of the two tests.
        A scope of None means the built-in data_loader fixture.
        """
        report = run_scoped_loader_tests(pytester, scope)
        assert report["clear_calls_after_teardown"] == expected_counts

    @pytest.mark.parametrize("file_name", ["file.txt", "file.json"])
    @pytest.mark.parametrize(
        ("scope", "expected_loads"),
        [(None, 4), ("function", 4), ("class", 2), ("module", 2), ("package", 1), ("session", 1)],
    )
    def test_data_cached_for_fixture_lifetime(
        self, pytester: Pytester, scope: str | None, expected_loads: int, file_name: str
    ) -> None:
        """Test that a data loader fixture loads a file once per fixture lifetime without using the session cache.

        The txt file has no file reader and the json file uses the built-in reader. Both are cached the same way.
        """
        report = run_scoped_loader_tests(pytester, scope, file_name=file_name, num_modules=2)
        assert report["file_loaders_created"] == expected_loads
        assert report["session_cache_reads"] == 0

    @pytest.mark.parametrize(
        ("scope", "expected"),
        [("function", "sub"), ("class", "sub"), ("module", "sub"), ("package", "root"), ("session", "root")],
    )
    def test_relative_path_search_location(self, pytester: Pytester, scope: str, expected: str) -> None:
        """Test that a relative path is searched from the test file for the function, class, and module scopes.

        The package and session scopes search from the file that created the fixture.
        """
        pytester.makefile(".txt", **{"data/file": "root", "sub/data/file": "sub"})
        pytester.makeconftest(f"""
        from pytest_data_loader import make_data_loader_fixture

        {SCOPED_FIXTURE} = make_data_loader_fixture(scope={scope!r})
        """)
        pytester.makepyfile(
            **{
                "sub/test_file": f"""
                def test_load({SCOPED_FIXTURE}):
                    assert {SCOPED_FIXTURE}("file.txt") == {expected!r}
                """
            }
        )
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_registered_reader_search_location(self, pytester: Pytester) -> None:
        """Test that a session scoped fixture uses the file readers registered for the file that created the fixture."""
        pytester.makefile(".yaml", **{"data/file": "content"})
        pytester.makeconftest(f"""
        from pytest_data_loader import make_data_loader_fixture, register_reader

        def reader(f):
            return "root", f.read()

        register_reader(".yaml", reader)
        {SCOPED_FIXTURE} = make_data_loader_fixture(scope="session")
        """)
        pytester.makepyfile(
            **{
                "sub/conftest": """
                from pytest_data_loader import register_reader

                def reader(f):
                    return "sub", f.read()

                register_reader(".yaml", reader)
                """,
                "sub/test_file": f"""
                def test_load({SCOPED_FIXTURE}, data_loader):
                    assert {SCOPED_FIXTURE}("file.yaml") == ("root", "content")
                    assert data_loader("file.yaml") == ("sub", "content")
                """,
            }
        )
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_jsonl_returns_fresh_iterator_across_tests(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that tests sharing a session scoped fixture each receive a fresh iterator for the same JSONL file."""
        (data_dir / "file.jsonl").write_text('{"k": 1}\n{"k": 2}\n')
        pytester.makeconftest(f"""
        from pytest_data_loader import make_data_loader_fixture

        {SCOPED_FIXTURE} = make_data_loader_fixture(scope="session")
        """)
        pytester.makepyfile(f"""
        def test_first({SCOPED_FIXTURE}):
            assert list({SCOPED_FIXTURE}("file.jsonl")) == [{{"k": 1}}, {{"k": 2}}]

        def test_second({SCOPED_FIXTURE}):
            assert list({SCOPED_FIXTURE}("file.jsonl")) == [{{"k": 1}}, {{"k": 2}}]
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    def test_on_missing_warn_once_per_fixture_lifetime(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that a missing path warns only once when tests share a session scoped fixture."""
        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {DataLoaderOnMissingAction.WARN.value}
        """)
        pytester.makeconftest(f"""
        from pytest_data_loader import make_data_loader_fixture

        {SCOPED_FIXTURE} = make_data_loader_fixture(scope="session")
        """)
        pytester.makepyfile(f"""
        def test_first({SCOPED_FIXTURE}):
            assert {SCOPED_FIXTURE}("does_not_exist.txt") is None

        def test_second({SCOPED_FIXTURE}):
            assert {SCOPED_FIXTURE}("does_not_exist.txt") is None
        """)
        result = pytester.runpytest("-v", "-W", "always")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)
        assert str(result.stdout).count("UserWarning: DataNotFound:") == 1
