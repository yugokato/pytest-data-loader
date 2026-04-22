import json
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

pytestmark = pytest.mark.plugin


class TestDataLoaderFixture:
    """Tests for the data_loader fixture."""

    @pytest.fixture
    def data_dir(self, pytester: Pytester) -> Path:
        return pytester.mkdir("data")

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

    def test_load_with_file_reader(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader passes file_reader to the underlying FileLoader."""
        (data_dir / "file.json").write_text(json.dumps({"k": "v"}))

        pytester.makepyfile("""
        import json

        def test_load(data_loader):
            data = data_loader("file.json", file_reader=json.load)
            assert data == {"k": "v"}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_load_with_onload_func(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that data_loader applies the onload_func to the loaded data."""
        (data_dir / "file.txt").write_text("hello")

        pytester.makepyfile("""
        def test_load(data_loader):
            data = data_loader("file.txt", onload_func=lambda d: d.upper())
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
            data = data_loader("file.bin", mode="rb")
            assert data == b"{data}"
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

    def test_cache_cleared_at_module_teardown(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that FileLoader instances created by data_loader are cleared by module teardown."""
        json_file = data_dir / "file.json"
        json_file.write_text(json.dumps({"key": "value"}))

        pytester.makeconftest("""
        import json
        import pytest
        from pytest_data_loader.loaders.impl import FileLoader

        _clear_cache_call_count = 0
        _original_clear_cache = FileLoader.clear_cache

        def _counting_clear_cache(self) -> None:
            global _clear_cache_call_count
            _clear_cache_call_count += 1
            _original_clear_cache(self)

        FileLoader.clear_cache = _counting_clear_cache

        def pytest_terminal_summary() -> None:
            FileLoader.clear_cache = _original_clear_cache
            print("CLEAR_CACHE_REPORT:" + json.dumps({"calls": _clear_cache_call_count}))
        """)
        pytester.makepyfile(f"""
        import json
        from pathlib import Path

        def test_load(data_loader):
            data = data_loader(Path({str(json_file)!r}))
            assert data == {{"key": "value"}}
        """)
        result = pytester.runpytest("-vs")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

        report_prefix = "CLEAR_CACHE_REPORT:"
        report_line = next((line for line in result.outlines if line.startswith(report_prefix)), None)
        assert report_line is not None
        report = json.loads(report_line[len(report_prefix) :])
        assert report["calls"] == 1

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
