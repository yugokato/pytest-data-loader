import pytest
from pytest import ExitCode

pytestmark = pytest.mark.plugin


class TestLoaderStacking:
    """Test stacking multiple data loader decorators on a single test function"""

    @pytest.fixture(autouse=True)
    def _setup_data(self, pytester: pytest.Pytester) -> None:
        pytester.mkdir("data")
        pytester.makefile(".json", **{"data/config": '{"key": "value"}'})
        pytester.makefile(".json", **{"data/extra": '{"x": 1}'})
        pytester.makefile(".json", **{"data/third": '{"z": 3}'})
        pytester.makefile(".txt", **{"data/rows": "alpha\nbeta\ngamma"})
        pytester.mkdir("data/items")
        pytester.makefile(".txt", **{"data/items/a": "item_a"})
        pytester.makefile(".txt", **{"data/items/b": "item_b"})

    def test_two_stacked_load(self, pytester: pytest.Pytester) -> None:
        """Test that two stacked @load decorators inject both fixtures into one test run."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("cfg", "config.json")
        @load("extra", "extra.json")
        def test_func(cfg, extra):
            assert cfg == {"key": "value"}
            assert extra == {"x": 1}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_three_stacked_load(self, pytester: pytest.Pytester) -> None:
        """Test that three stacked @load decorators all inject their fixtures correctly."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("cfg", "config.json")
        @load("extra", "extra.json")
        @load("third", "third.json")
        def test_func(cfg, extra, third):
            assert cfg == {"key": "value"}
            assert extra == {"x": 1}
            assert third == {"z": 3}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_stacked_load_two_name_form(self, pytester: pytest.Pytester) -> None:
        """Test that stacked @load decorators support mixing single-name and two-name fixture forms."""
        pytester.makepyfile("""
        from pathlib import Path
        from pytest_data_loader import load

        @load("cfg", "config.json")
        @load(("file_path", "extra"), "extra.json")
        def test_func(cfg, file_path, extra):
            assert cfg == {"key": "value"}
            assert isinstance(file_path, Path)
            assert file_path.name == "extra.json"
            assert extra == {"x": 1}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_fixture_name_collision_is_restricted(self, pytester: pytest.Pytester) -> None:
        """Test that stacking decorators with duplicate fixture names raises ValueError at collection time."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("data", "config.json")
        @load("data", "extra.json")
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "Duplicate fixture name" in str(result.stdout)

    def test_fixture_name_collision_two_name_form(self, pytester: pytest.Pytester) -> None:
        """Test that collisions in two-name fixture form (e.g. 'file_path') are also caught."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load(("file_path", "cfg"), "config.json")
        @load(("file_path", "extra"), "extra.json")
        def test_func(file_path, cfg, extra):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "Duplicate fixture name" in str(result.stdout)

    def test_load_and_parametrize_stacked(self, pytester: pytest.Pytester) -> None:
        """Test that @load and @parametrize stacked produce N runs each with the loaded fixture."""
        pytester.makepyfile("""
        from pytest_data_loader import load, parametrize

        @load("cfg", "config.json")
        @parametrize("row", "rows.txt")
        def test_func(cfg, row):
            assert cfg == {"key": "value"}
            assert row in ("alpha", "beta", "gamma")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    def test_load_and_parametrize_dir_stacked(self, pytester: pytest.Pytester) -> None:
        """Test that @load and @parametrize_dir stacked produce one run per directory file."""
        pytester.makepyfile("""
        from pytest_data_loader import load, parametrize_dir

        @load("cfg", "config.json")
        @parametrize_dir("item", "items")
        def test_func(cfg, item):
            assert cfg == {"key": "value"}
            assert item in ("item_a", "item_b")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize(
        ("lazy_loading1", "lazy_loading2"), [(True, True), (True, False), (False, True), (False, False)]
    )
    def test_mixed_lazy_and_eager_load(
        self, pytester: pytest.Pytester, lazy_loading1: bool, lazy_loading2: bool
    ) -> None:
        """Test that stacking @load with mixed lazy_loading settings works correctly."""
        pytester.makepyfile(f"""
        from pytest_data_loader import load, parametrize

        @load("cfg", "config.json", lazy_loading={lazy_loading1})
        @parametrize("row", "rows.txt", lazy_loading={lazy_loading2})
        def test_func(cfg, row):
            assert cfg == {{"key": "value"}}
            assert row in ("alpha", "beta", "gamma")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    def test_stacked_error_includes_loader_info(self, pytester: pytest.Pytester) -> None:
        """Test that collection errors from stacked data loaders identify which decorator failed."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("cfg", "config.json")
        @load("missing", "nonexistent_file.json")
        def test_func(cfg, missing):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "@load(fixture_names=('missing',), path='nonexistent_file.json')" in output

    def test_stacked_with_pytest_parametrize_mark(self, pytester: pytest.Pytester) -> None:
        """Test that stacking @load with @pytest.mark.parametrize produces a Cartesian product."""
        pytester.makepyfile("""
        import pytest
        from pytest_data_loader import load

        @pytest.mark.parametrize("x", [1, 2])
        @load("cfg", "config.json")
        def test_func(cfg, x):
            assert cfg == {"key": "value"}
            assert x in (1, 2)
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    def test_two_parametrize_stacked_cartesian(self, pytester: pytest.Pytester) -> None:
        """Test that two stacked @parametrize decorators produce a Cartesian product of N x M runs."""
        pytester.makefile(".txt", **{"data/rows2": "x\ny"})
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("row1", "rows.txt")
        @parametrize("row2", "rows2.txt")
        def test_func(row1, row2):
            assert row1 in ("alpha", "beta", "gamma")
            assert row2 in ("x", "y")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        # 3 rows x 2 rows = 6 combinations
        result.assert_outcomes(passed=6)

    def test_decorator_order_outer_axis(self, pytester: pytest.Pytester) -> None:
        """Test that the top (visually outermost) data loader is the slowest-varying axis in test IDs."""
        pytester.makefile(".txt", **{"data/rows2": "x\ny"})
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("row1", "rows.txt")
        @parametrize("row2", "rows2.txt")
        def test_func(row1, row2):
            pass
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        lines = result.stdout.lines
        test_lines = [line for line in lines if "test_func[" in line]
        # top data loader decorator (@parametrize "row1") is the slowest-varying (outer) axis.
        # With lazy loading IDs are "rows.txt:partN-rows2.txt:partM".
        # Expect: part1 of row1 in first 2 runs, part2 in next 2, part3 in last 2.
        assert len(test_lines) == 6
        assert "rows.txt:part1" in test_lines[0] and "rows.txt:part1" in test_lines[1]
        assert "rows.txt:part2" in test_lines[2] and "rows.txt:part2" in test_lines[3]
        assert "rows.txt:part3" in test_lines[4] and "rows.txt:part3" in test_lines[5]

    def test_stacked_loaders_read_file_from_cache(self, pytester: pytest.Pytester) -> None:
        """Test that each file in stacked data loaders is opened only once per test function, not per Cartesian test."""
        _tracked_files = {"config.json", "rows.txt", "a.txt", "b.txt"}
        pytester.makeconftest(f"""
        import builtins
        from pathlib import Path

        _open = builtins.open
        _tracked = {_tracked_files!r}
        counter = {{}}

        def _counting_open(file, *args, **kwargs):
            file_name = Path(file).name if isinstance(file, str | Path) else None
            if file_name in _tracked:
                counter[file_name] = counter.get(file_name, 0) + 1
            return _open(file, *args, **kwargs)

        builtins.open = _counting_open
        """)
        pytester.makepyfile("""
        from conftest import counter
        from pytest_data_loader import load, parametrize, parametrize_dir

        @load("cfg", "config.json")
        @parametrize("row", "rows.txt")
        @parametrize_dir("item", "items")
        def test_func(cfg, row, item):
            assert cfg == {"key": "value"}
            assert row in ("alpha", "beta", "gamma")
            assert item in ("item_a", "item_b")

        def test_open_counts():
            # @load: opened exactly once at first test setup (subsequent tests reuse it via lru_cache)
            assert counter.get("config.json", 0) == 1

            # @parametrize: 1 scan open (collection) + 1 lazy-load open
            # (subsequent tests reuse it via _cached_file_objects)
            assert counter.get("rows.txt", 0) == 2

            # @parametrize_dir: Each dir file is opened exactly once at first test setup
            # (subsequent tests reuse it via lru_cache)
            for file in ("a.txt", "b.txt"):
                assert counter.get(file, 0) == 1
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        # 1 (load) x 3 (rows) x 2 (items) = 6 Cartesian tests + 1 verification test
        result.assert_outcomes(passed=7)
