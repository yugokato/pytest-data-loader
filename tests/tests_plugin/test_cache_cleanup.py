"""Tests for the _pytest_data_loader_cleanup module-scoped fixture"""

import json

import pytest
from pytest import ExitCode, Pytester

pytestmark = pytest.mark.plugin


class TestCacheCleanup:
    """Tests for the _pytest_data_loader_cleanup module-scoped fixture."""

    def test_cache_cleared_at_module_teardown(self, pytester: Pytester) -> None:
        """Test that the _pytest_data_loader_cleanup fixture calls clear_cache on all loaders at module teardown"""
        # Create a JSON file so that the loader caches a file handle (file_reader keeps it open)
        test_data_dir = pytester.mkdir("data")
        json_file = test_data_dir / "file.json"
        json_file.write_text(json.dumps({"key": "value"}))

        # Patch FileDataLoader.clear_cache to count invocations across the entire session
        pytester.makeconftest("""
import json
import pytest
from pytest_data_loader.loaders.impl import FileDataLoader

_clear_cache_call_count = 0
_original_clear_cache = FileDataLoader.clear_cache


def _counting_clear_cache(self) -> None:
    global _clear_cache_call_count
    _clear_cache_call_count += 1
    _original_clear_cache(self)


FileDataLoader.clear_cache = _counting_clear_cache


def pytest_terminal_summary() -> None:
    FileDataLoader.clear_cache = _original_clear_cache
    print("CLEAR_CACHE_REPORT:" + json.dumps({"calls": _clear_cache_call_count}))
""")

        # Test module: one test using @load with lazy_loading=True on an absolute JSON path
        pytester.makepyfile(f"""
from pathlib import Path
from pytest_data_loader import load

@load("data", Path({str(json_file)!r}), lazy_loading=True)
def test_load_json(data):
    '''Test that data is loaded correctly'''
    assert data == {{"key": "value"}}
""")

        result = pytester.runpytest("-vs")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

        # Parse the clear_cache call count reported by the conftest
        report_prefix = "CLEAR_CACHE_REPORT:"
        report_line = next((line for line in result.outlines if line.startswith(report_prefix)), None)
        assert report_line is not None, f"CLEAR_CACHE_REPORT not found in output:\n{result.stdout.str()}"
        report = json.loads(report_line[len(report_prefix) :])

        # clear_cache() must be called exactly once by the module cleanup fixture at teardown
        assert report["calls"] == 1, (
            f"Expected clear_cache to be called exactly once at module teardown, got {report['calls']}"
        )
