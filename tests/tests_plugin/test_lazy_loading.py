import json
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

from pytest_data_loader import parametrize
from pytest_data_loader.types import DataLoader, LazyLoadedData, LazyLoadedPartData

from .helper import TestContext, create_test_context, run_pytest_with_context

pytestmark = pytest.mark.plugin


class TestLazyLoading:
    """Tests for lazy loading behavior."""

    @pytest.mark.parametrize("collect_only", [True, False])
    @pytest.mark.parametrize("file_extension", [".txt", ".json", ".jsonl", ".yml", ".png"], indirect=True)
    @pytest.mark.parametrize("lazy_loading", [False, True])
    def test_lazy_loading(
        self, test_context: TestContext, lazy_loading: bool, collect_only: bool, file_extension: str
    ) -> None:
        """Test that data is always loaded lazily when lazy loading is enabled.

        When lazy loading is enabled, the fixture setup should receive the value as either
        LazyLoadedData or LazyLoadedPartData.
        """
        if file_extension == ".png" and test_context.loader == parametrize:
            # Not supported. The validation is tested in another test
            pytest.skip("Not applicable")

        pytester = test_context.pytester
        fixture_name = "arg1"

        if test_context.loader == parametrize:
            pytester.makeconftest(f"""
            import pytest
            from pytest_data_loader.types import LazyLoadedPartData

            @pytest.hookimpl(tryfirst=True)
            def pytest_fixture_setup(request) -> None:
                assert request.fixturename in request.fixturenames
                if request.fixturename == '{fixture_name}':
                    v = request.param
                    if {lazy_loading}:
                        assert isinstance(v, {LazyLoadedPartData.__name__}), (
                            f"Expected a {LazyLoadedPartData.__name__} instance, got {{type(v).__name__}}"
                        )
                        idx =  request.node.callspec.indices[request.fixturename]
                        assert request.node.name.endswith(f"[{Path(test_context.path).name}:part{{idx+1}}]")
                    else:
                        assert isinstance(v, type(v))
                        assert request.node.name.endswith(f"[{{repr(v)}}]")
            """)
        else:
            pytester.makeconftest(f"""
            import pytest
            from pytest_data_loader.types import LazyLoadedData

            @pytest.hookimpl(tryfirst=True)
            def pytest_fixture_setup(request) -> None:
                assert request.fixturename in request.fixturenames
                if request.fixturename == '{fixture_name}':
                    v = request.param
                    if {lazy_loading}:
                        assert isinstance(v, {LazyLoadedData.__name__}), (
                            f"Expected a {LazyLoadedData.__name__} instance, got {{type(v).__name__}}"
                        )
                    else:
                        assert isinstance(v, type(v))
            """)

        result = run_pytest_with_context(
            test_context, fixture_name, lazy_loading=lazy_loading, collect_only=collect_only
        )
        assert result.ret == ExitCode.OK
        if not collect_only:
            result.assert_outcomes(passed=test_context.num_expected_tests)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("file_extension", [".txt", ".json", ".yml"], indirect=True)
    def test_lazy_loading_io_timing(self, test_context: TestContext, lazy_loading: bool, file_extension: str) -> None:
        """Test that file I/O actually occurs at the expected phase (collection vs setup).

        File opens for the auto-mode binary probe (mode="rb") are excluded here. Only meaningful data reads are
        counted.  The probe is memoized per session so it runs at most once per (file, encoding) combination across
        all FileLoader instances, but it is still excluded here because it is an implementation detail rather than a
        data I/O.

        Expected opens (collection time, setup ime) per (loader, lazy_loading, file_extension):

        Loader              lazy    .txt    .json   .yml
        ----------------    -----   ------  ------  ------
        @load               True    (0, 1)  (0, 1)  (0, 1)
        @load               False   (1, 0)  (1, 0)  (1, 0)
        @parametrize        True    (1, 1)  (1, 0)  (1, 0)
        @parametrize        False   (1, 0)  (1, 0)  (1, 0)
        @parametrize_dir    True    (0, 2)  (0, 2)  (0, 2)
        @parametrize_dir    False   (2, 0)  (2, 0)  (2, 0)

        Open count notes:
        - .txt: streamable. _scan_text_file() opens once at collection; setup draws from the session
          handle pool (1 open on first case, cache hit on subsequent cases).
        - .json: file_reader (json.load) → non-streamable. _load_now() opens a per-instance handle
          at collection; the same handle is reused at setup via _file_handles → 0 setup opens.
        - .yml: non-streamable, no file_reader. Lazy @parametrize caches raw bytes at collection;
          setup is a content-cache hit → 0 setup opens.
        - @parametrize_dir: DirectoryLoader with 2 child FileLoaders; counts are @load counts x 2.
        """
        pytester = test_context.pytester

        pytester.makeconftest("""
        import builtins
        import json

        import pytest

        _original_open = builtins.open
        _io_log = []
        _current_phase = "collection"

        def _tracking_open(file, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            _io_log.append((_current_phase, str(file), mode))
            return _original_open(file, *args, **kwargs)


        builtins.open = _tracking_open


        def pytest_collection_modifyitems():
            global _current_phase
            _current_phase = "between"


        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_setup():
            global _current_phase
            _current_phase = "setup"
            yield
            _current_phase = "between"


        def pytest_terminal_summary():
            builtins.open = _original_open
            print("IO_TIMING_REPORT:" + json.dumps(_io_log))
        """)

        result = run_pytest_with_context(test_context, "arg1", lazy_loading=lazy_loading)
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=test_context.num_expected_tests)

        # Parse IO timing report from inner pytest stdout
        report_prefix = "IO_TIMING_REPORT:"
        report_line = next((line for line in result.outlines if line.startswith(report_prefix)), None)
        assert report_line is not None
        io_log: list[list[str]] = json.loads(report_line[len(report_prefix) :])

        # Filter to data-read opens (exclude the auto-mode binary probe, which is
        # memoized per session but still occurs on each instance's first _detect_read_mode call).
        data_opens = [
            (phase, path)
            for phase, path, mode in io_log
            if Path(path).is_relative_to(test_context.data_dir) and mode != "rb"
        ]
        collection_opens = sum(1 for phase, _ in data_opens if phase == "collection")
        setup_opens = sum(1 for phase, _ in data_opens if phase == "setup")

        expected_opens: dict[tuple[str, str, bool], tuple[int, int]] = {
            ("load", ".txt", True): (0, 1),
            ("load", ".json", True): (0, 1),
            ("load", ".yml", True): (0, 1),
            ("load", ".txt", False): (1, 0),
            ("load", ".json", False): (1, 0),
            ("load", ".yml", False): (1, 0),
            ("parametrize", ".txt", True): (1, 1),
            ("parametrize", ".json", True): (1, 0),
            ("parametrize", ".yml", True): (1, 0),
            ("parametrize", ".txt", False): (1, 0),
            ("parametrize", ".json", False): (1, 0),
            ("parametrize", ".yml", False): (1, 0),
            ("parametrize_dir", ".txt", True): (0, 2),
            ("parametrize_dir", ".json", True): (0, 2),
            ("parametrize_dir", ".yml", True): (0, 2),
            ("parametrize_dir", ".txt", False): (2, 0),
            ("parametrize_dir", ".json", False): (2, 0),
            ("parametrize_dir", ".yml", False): (2, 0),
        }
        loader_name = test_context.loader.__name__
        expected_collection, expected_setup = expected_opens[(loader_name, file_extension, lazy_loading)]
        combo = f"loader={loader_name!r}, ext={file_extension!r}, lazy={lazy_loading}"
        assert collection_opens == expected_collection, (
            f"{combo}: expected {expected_collection} collection open(s), got {collection_opens}. "
            f"data_opens={data_opens}"
        )
        assert setup_opens == expected_setup, (
            f"{combo}: expected {expected_setup} setup open(s), got {setup_opens}. data_opens={data_opens}"
        )

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("file_extension", [".txt", ".json", ".yml"], indirect=True)
    def test_lazy_loading_memory_usage(
        self, pytester: Pytester, loader: DataLoader, lazy_loading: bool, file_extension: str
    ) -> None:
        """Test that lazy loading reduces the memory footprint of parametrized values stored by pytest after collection.

        With eager loading, pytest stores the full loaded data in callspec.params for the entire session.
        With lazy loading, it stores lightweight lazy objects that hold only a callable reference and metadata.
        """
        # Generate large test data (~100KB) to make the memory difference measurable
        num_chars = 2048
        num_lines = 50
        if file_extension == ".txt":
            line = "x" * num_chars  # ~2KB per line
            file_content = "\n".join(line for _ in range(num_lines))
        elif file_extension == ".yml":
            file_content = "\n".join(f"k{i:02d}: {'x' * num_chars}" for i in range(num_lines))
        else:  # .json
            entries = {f"key{i:02d}": "x" * num_chars for i in range(num_lines)}
            file_content = json.dumps(entries)

        test_context = create_test_context(pytester, loader, file_extension=file_extension, file_content=file_content)

        pytester.makeconftest("""
        import sys
        import json
        import pytest


        def _get_data_size(obj, _seen=None):
            if _seen is None:
                _seen = set()
            obj_id = id(obj)
            if obj_id in _seen:
                return 0
            _seen.add(obj_id)
            size = sys.getsizeof(obj)
            if isinstance(obj, dict):
                for k, v in obj.items():
                    size += _get_data_size(k, _seen)
                    size += _get_data_size(v, _seen)
            elif isinstance(obj, (list, tuple, set, frozenset)):
                for item in obj:
                    size += _get_data_size(item, _seen)
            return size


        _total_param_size = 0


        def pytest_collection_modifyitems(items):
            global _total_param_size
            for item in items:
                if hasattr(item, "callspec"):
                    for v in item.callspec.params.values():
                        _total_param_size += _get_data_size(v)


        @pytest.hookimpl(wrapper=True)
        def pytest_terminal_summary():
            yield
            print("MEMORY_REPORT:" + json.dumps({"total_param_size": _total_param_size}))
        """)

        result = run_pytest_with_context(test_context, "arg1", lazy_loading=lazy_loading)
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=test_context.num_expected_tests)

        # Parse memory report from inner pytest stdout
        report_prefix = "MEMORY_REPORT:"
        report_line = next((line for line in result.outlines if line.startswith(report_prefix)), None)
        assert report_line is not None
        report = json.loads(report_line[len(report_prefix) :])
        total_param_size = report["total_param_size"]

        # Compute expected data size in bytes; parametrize_dir creates 2 files
        data_size_bytes = len(file_content.encode("utf-8"))
        if not loader.is_file_loader:
            data_size_bytes *= 2

        if lazy_loading:
            assert total_param_size < data_size_bytes * 0.5, (
                f"Lazy loading should use less memory than the actual data size. "
                f"total_param_size={total_param_size}, data_size_bytes={data_size_bytes}"
            )
        else:
            assert total_param_size >= data_size_bytes, (
                f"Eager loading should use at least the data size. "
                f"total_param_size={total_param_size}, data_size_bytes={data_size_bytes}"
            )


class TestGeneratorCaching:
    """Test that one-shot iterator values from file readers are not cached across resolve calls."""

    def test_jsonl_load_with_stacked_parametrize_all_items_get_full_data(self, pytester: Pytester) -> None:
        """Test that all stacked-parametrize items each receive the full JSONL iterator.

        When a LazyLoadedData produced by @load is shared across N test items (cartesian product with a
        stacked @pytest.mark.parametrize), each item's resolve() must yield a fresh generator — not a
        replayed exhausted one from the _loaded_data cache.
        """
        data_dir = pytester.mkdir("data")
        (data_dir / "file.jsonl").write_text('{"k": 1}\n{"k": 2}\n')

        pytester.makepyfile("""
        import pytest
        from pytest_data_loader import load

        @load("data", "file.jsonl")
        @pytest.mark.parametrize("x", [1, 2, 3])
        def test_load_stacked(data, x):
            items = list(data)
            assert len(items) == 2, f"Expected 2 items for x={x}, got {items!r}"
            assert items[0] == {"k": 1}
            assert items[1] == {"k": 2}
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)
