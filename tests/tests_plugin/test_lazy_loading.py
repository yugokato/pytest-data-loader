import json
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

from pytest_data_loader import parametrize
from pytest_data_loader.types import DataLoader, LazyLoadedData, LazyLoadedPartData
from tests.tests_plugin.helper import TestContext, create_test_context, run_pytest_with_context

pytestmark = pytest.mark.plugin


@pytest.mark.parametrize("collect_only", [True, False])
@pytest.mark.parametrize("file_extension", [".txt", ".json", ".png"], indirect=True)
@pytest.mark.parametrize("lazy_loading", [False, True])
def test_lazy_loading(test_context: TestContext, lazy_loading: bool, collect_only: bool, file_extension: str) -> None:
    """Test that data is always loaded lazily when lazy loading is enabled. When lazy loading is enabled, the fixture
    setup should receive the value as either LazyLoadedData or LazyLoadedPartData
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

    result = run_pytest_with_context(test_context, fixture_name, lazy_loading=lazy_loading, collect_only=collect_only)
    assert result.ret == ExitCode.OK
    if not collect_only:
        result.assert_outcomes(passed=test_context.num_expected_tests)


@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("file_extension", [".txt", ".json"], indirect=True)
def test_lazy_loading_io_timing(test_context: TestContext, lazy_loading: bool, file_extension: str) -> None:
    """Test that file I/O actually occurs at the expected phase (collection vs setup).

    Expected behavior per loader:
      @load:            lazy_loading=True  -> collection=0, setup>0
      @load:            lazy_loading=False -> collection>0, setup=0
      @parametrize:     lazy_loading=True  -> collection>0 (scan to count items), setup>0 (load data)
      @parametrize:     lazy_loading=False -> collection>0, setup=0
      @parametrize_dir: lazy_loading=True  -> collection=0, setup>0
      @parametrize_dir: lazy_loading=False -> collection>0, setup=0
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
    _io_log.append((_current_phase, str(file)))
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

    # Filter to only opens of files inside the test data directory
    data_opens = [(phase, path) for phase, path in io_log if Path(path).is_relative_to(test_context.data_dir)]
    collection_opens = sum(1 for phase, _ in data_opens if phase == "collection")
    setup_opens = sum(1 for phase, _ in data_opens if phase == "setup")

    if lazy_loading:
        # @parametrize scans the file during collection phase to count parametrized items.
        # @load and @parametrize_dir defer all I/O to setup phase
        if test_context.loader == parametrize:
            assert collection_opens > 0
        else:
            assert collection_opens == 0
        assert setup_opens > 0
    else:
        # Eager: file is read during collection; no I/O at setup
        assert collection_opens > 0
        assert setup_opens == 0


@pytest.mark.parametrize("lazy_loading", [True, False])
@pytest.mark.parametrize("file_extension", [".txt", ".json"], indirect=True)
def test_lazy_loading_memory_usage(
    pytester: Pytester, loader: DataLoader, lazy_loading: bool, file_extension: str
) -> None:
    """Test that lazy loading reduces the memory footprint of parametrized values stored by pytest after collection.

    With eager loading, pytest stores the full loaded data in callspec.params for the entire session.
    With lazy loading, it stores lightweight lazy objects that hold only a callable reference and metadata.
    """
    # Generate large test data (~100KB) to make the memory difference measurable
    if file_extension == ".txt":
        line = "x" * 2048  # ~2KB per line
        file_content = "\n".join(line for _ in range(50))
    else:  # .json
        entries = {f"key{i:02d}": "x" * 2048 for i in range(50)}
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
