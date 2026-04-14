import pytest
from pytest import ExitCode

pytestmark = pytest.mark.plugin


class TestParametrizeMultiPaths:
    """Test multi paths scenarios for @parametrize loader"""

    @pytest.fixture(autouse=True)
    def _setup_data(self, pytester: pytest.Pytester) -> None:
        pytester.mkdir("data")
        pytester.makefile(".txt", **{"data/file1": "alpha\nbeta"})
        pytester.makefile(".txt", **{"data/file2": "gamma\ndelta"})
        pytester.makefile(".json", **{"data/a": '["x", "y"]'})
        pytester.makefile(".json", **{"data/b": '["z"]'})

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_multi_file_txt(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that @parametrize with a list of paths concatenates data from all files."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", ["file1.txt", "file2.txt"], lazy_loading={lazy_loading})
        def test_func(data):
            assert data in ("alpha", "beta", "gamma", "delta")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_multi_file_json(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that @parametrize with a list of JSON files concatenates parsed data from all files."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", ["a.json", "b.json"], lazy_loading={lazy_loading})
        def test_func(data):
            assert data in ("x", "y", "z")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_multi_file_with_file_path(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that file_path fixture correctly reflects each source file in multi-path mode."""
        pytester.makepyfile(f"""
        from pathlib import Path
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), ["file1.txt", "file2.txt"], lazy_loading={lazy_loading})
        def test_func(file_path, data):
            assert isinstance(file_path, Path)
            if data in ("alpha", "beta"):
                assert file_path.name == "file1.txt"
            else:
                assert file_path.name == "file2.txt"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_multi_file_with_filter_func(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that filter_func applies correctly across multiple files in multi-path mode."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", ["file1.txt", "file2.txt"], lazy_loading={lazy_loading}, filter_func=lambda d: d != "beta")
        def test_func(data):
            assert data in ("alpha", "gamma", "delta")
            assert data != "beta"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_multi_file_with_process_func(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that process_func applies correctly across multiple files in multi-path mode."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", ["file1.txt", "file2.txt"], lazy_loading={lazy_loading}, process_func=lambda d: d.upper())
        def test_func(data):
            assert data in ("ALPHA", "BETA", "GAMMA", "DELTA")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    def test_parametrize_multi_file_duplicate_paths(self, pytester: pytest.Pytester) -> None:
        """Test that the same file can be listed twice, resulting in duplicate parametrized cases."""
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("data", ["file1.txt", "file1.txt"])
        def test_func(data):
            assert data in ("alpha", "beta")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    def test_parametrize_empty_path_list_raises_error(self, pytester: pytest.Pytester) -> None:
        """Test that @parametrize with an empty path list raises a validation error."""
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("data", [])
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "empty" in str(result.stdout)


class TestParametrizeDirMultiPaths:
    """Test multi paths scenarios for @parametrize_dir loader"""

    @pytest.fixture(autouse=True)
    def _setup_data(self, pytester: pytest.Pytester) -> None:
        pytester.mkdir("data")
        pytester.mkdir("data/dir1")
        pytester.mkdir("data/dir2")
        pytester.makefile(".txt", **{"data/dir1/file_a": "alpha"})
        pytester.makefile(".txt", **{"data/dir1/file_b": "beta"})
        pytester.makefile(".txt", **{"data/dir2/file_c": "gamma"})
        pytester.makefile(".txt", **{"data/dir2/file_d": "delta"})

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_dir_multi_dir_basic(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that @parametrize_dir with a list of paths concatenates data from all directories."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", ["dir1", "dir2"], lazy_loading={lazy_loading})
        def test_func(data):
            assert data in ("alpha", "beta", "gamma", "delta"), f"unexpected: {{data!r}}"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_dir_multi_dir_with_file_path(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that file_path fixture correctly reflects each source file in multi-dir mode."""
        pytester.makepyfile(f"""
        from pathlib import Path
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(("file_path", "data"), ["dir1", "dir2"], lazy_loading={lazy_loading})
        def test_func(file_path, data):
            assert isinstance(file_path, Path)
            if data in ("alpha", "beta"):
                assert file_path.parent.name == "dir1"
            else:
                assert file_path.parent.name == "dir2"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_dir_multi_dir_with_filter_func(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that filter_func applies correctly across multiple directories in multi-dir mode."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", ["dir1", "dir2"], lazy_loading={lazy_loading},
                         filter_func=lambda p: p.name != "file_a.txt")
        def test_func(data):
            assert data in ("beta", "gamma", "delta")
            assert data != "alpha"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_parametrize_dir_multi_dir_with_process_func(self, pytester: pytest.Pytester, lazy_loading: bool) -> None:
        """Test that process_func applies correctly across multiple directories in multi-dir mode."""
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", ["dir1", "dir2"], lazy_loading={lazy_loading},
                         process_func=lambda d: d.strip().upper())
        def test_func(data):
            assert data in ("ALPHA", "BETA", "GAMMA", "DELTA")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    def test_parametrize_dir_multi_dir_with_recursive(self, pytester: pytest.Pytester) -> None:
        """Test that recursive=True collects files from subdirectories across all listed directories."""
        pytester.mkdir("data/dir1/sub")
        pytester.mkdir("data/dir2/sub")
        pytester.makefile(".txt", **{"data/dir1/sub/file_c": "foo"})
        pytester.makefile(".txt", **{"data/dir2/sub/file_d": "bar"})
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", ["dir1", "dir2"], recursive=True)
        def test_func(data):
            assert data in ("alpha", "beta", "foo", "gamma", "delta", "bar")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=6)

    def test_parametrize_dir_multi_dir_with_file_reader_func(self, pytester: pytest.Pytester) -> None:
        """Test that file_reader_func selects correct readers per file in multi-dir mode."""
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        def my_reader(path):
            return lambda f: f.read().upper()

        @parametrize_dir("data", ["dir1", "dir2"], file_reader_func=my_reader)
        def test_func(data):
            assert data in ("ALPHA", "BETA", "GAMMA", "DELTA")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    def test_parametrize_dir_multi_dir_duplicate_dirs(self, pytester: pytest.Pytester) -> None:
        """Test that the same directory listed twice results in duplicate parametrized cases."""
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", ["dir1", "dir1"])
        def test_func(data):
            assert data in ("alpha", "beta")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    def test_parametrize_dir_empty_path_list_raises_error(self, pytester: pytest.Pytester) -> None:
        """Test that @parametrize_dir with an empty path list raises a validation error."""
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", [])
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "empty" in str(result.stdout)

    def test_parametrize_dir_multi_dir_file_path_in_list_raises_error(self, pytester: pytest.Pytester) -> None:
        """Test that passing a file path in the multi-path list for @parametrize_dir raises a validation error."""
        pytester.makepyfile("""
        from pathlib import Path
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", [Path("dir1", "file_a.txt"), "dir1"])
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "Unable to locate the specified directory" in str(result.stdout)


class TestLoadMultiPath:
    """Tests for multi-path behavior of @load loader."""

    def test_load_multi_path_not_supported(self, pytester: pytest.Pytester) -> None:
        """Test that @load does not support multi-path and raises an error."""
        pytester.makepyfile("""
    from pytest_data_loader import load

    @load("data", ["file1.txt", "file2.txt"])
    def test_func(data):
        pass
    """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert "Multi-path is not supported for @load loader" in str(result.stdout)
