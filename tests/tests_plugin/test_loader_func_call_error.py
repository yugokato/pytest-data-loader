import pytest
from pytest import ExitCode, Pytester

pytestmark = pytest.mark.plugin


class TestLoaderFuncCallError:
    """Tests that loader function call errors include the file path in the exception message."""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_onload_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that onload_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".json", **{"data/data": '{"key": "value"}'})
        pytester.makepyfile(f"""
    from pytest_data_loader import load

    def f(d):
        raise ValueError("loader func error")

    @load("data", "data.json", lazy_loading={lazy_loading}, onload_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        if lazy_loading:
            assert result.ret == ExitCode.TESTS_FAILED
        else:
            assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "ValueError: loader func error" in output
        assert "Error while processing onload_func for 'data.json'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrizer_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that parametrizer_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/data": "foo\nbar"})
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize

    def f(d):
        raise ValueError("loader func error")

    @parametrize("data", "data.txt", lazy_loading={lazy_loading}, parametrizer_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "ValueError: loader func error" in output
        assert "Error while processing parametrizer_func for 'data.txt'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_filter_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that filter_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/data": "foo\nbar"})
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize

    def f(d):
        raise ValueError("loader func error")

    @parametrize("data", "data.txt", lazy_loading={lazy_loading}, filter_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "filter_func" in output
        assert "ValueError: loader func error" in output
        assert "Error while processing filter_func for 'data.txt'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_process_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that process_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/data": "foo\nbar"})
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize

    def f(d):
        raise ValueError("loader func error")

    @parametrize("data", "data.txt", lazy_loading={lazy_loading}, process_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        if lazy_loading:
            assert result.ret == ExitCode.TESTS_FAILED
        else:
            assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "ValueError: loader func error" in output
        assert "Error while processing process_func for 'data.txt'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_id_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that id_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/data": "foo\nbar"})
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize

    def f(p, d):
        raise ValueError("loader func error")

    @parametrize("data", "data.txt", lazy_loading={lazy_loading}, id_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "ValueError: loader func error" in output
        assert "Error while processing id_func for 'data.txt'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_marker_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that marker_func errors include the file path in the exception message."""
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/data": "foo\nbar"})
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize

    def f(p, d):
        raise ValueError("loader func error")

    @parametrize("data", "data.txt", lazy_loading={lazy_loading}, marker_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert "ValueError: loader func error" in output
        assert "Error while processing marker_func for 'data.txt'" in output

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_read_option_func_error(self, pytester: Pytester, lazy_loading: bool) -> None:
        """Test that read_option_func errors include the file path in the exception message."""
        data_dir = pytester.mkdir("data") / "mydir"
        data_dir.mkdir()
        (data_dir / "file1.txt").write_text("hello")
        pytester.makepyfile(f"""
    from pytest_data_loader import parametrize_dir

    def f(p):
        raise ValueError("loader func error")

    @parametrize_dir("data", "mydir", lazy_loading={lazy_loading}, read_option_func=f)
    def test_func(data):
        pass
    """)
        result = pytester.runpytest()
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout) + str(result.stderr)
        assert "ValueError: loader func error" in output
        assert "Error while processing read_option_func for 'file1.txt'" in output
