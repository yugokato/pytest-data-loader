import pytest
from pytest import ExitCode

pytestmark = pytest.mark.plugin


class TestTestGenerationError:
    """Test error handling in the pytest_generate_tests call"""

    def test_error_includes_loader_def(self, pytester: pytest.Pytester) -> None:
        """Test that test generation errors from the data loader show the actual failing data loader definition."""
        erring_data_loader_def = '@load("missing", "nonexistent.json")'
        pytester.makepyfile(f"""
        from pytest_data_loader import load

        {erring_data_loader_def}
        def test_func(cfg, missing):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert f"data loader: {erring_data_loader_def}" in output

    def test_error_with_module_prefixed_loader_def(self, pytester: pytest.Pytester) -> None:
        """Test that a module-prefixed data loader is shown correctly in the error."""
        erring_data_loader_def = '@pytest_data_loader.load("missing", "nonexistent.json")'
        pytester.makepyfile(f"""
        import pytest_data_loader

        {erring_data_loader_def}
        def test_func(missing):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert erring_data_loader_def in str(result.stdout)

    def test_error_with_aliased_loader_def(self, pytester: pytest.Pytester) -> None:
        """Test that a data loader imported under an alias is shown verbatim in the error."""
        erring_data_loader_def = '@L("missing", "nonexistent_file.json")'
        pytester.makepyfile(f"""
           from pytest_data_loader import load as L

           {erring_data_loader_def}
           def test_func(missing):
               pass
           """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert erring_data_loader_def in str(result.stdout)

    def test_error_with_multiline_loader_def(self, pytester: pytest.Pytester) -> None:
        """Test that a multi-line failing data loader is collapsed to a single line in the error note."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load(
            "missing",
            "nonexistent.json",
            lazy_loading=False,
        )
        def test_func(missing):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        assert 'data loader: @load( "missing", "nonexistent.json", lazy_loading=False, )' in str(result.stdout)

    @pytest.mark.parametrize("import_with_star", [False, True])
    def test_stacked_error_pinpoints_failing_loader_def(
        self, pytester: pytest.Pytester, import_with_star: bool
    ) -> None:
        """Test that when one of multiple stacked data loaders fails, only the failing one appears in the error.
        Also makes sure that error in @parametrize does not falsely pick the @pytest.mark.parametrize def
        """
        if import_with_star:
            import_code = "from pytest_data_loader import *"
        else:
            import_code = "from pytest_data_loader import load, parametrize"
        erring_data_loader_def = '@parametrize("missing", "nonexistent.json")'
        pytester.mkdir("data")
        pytester.makefile(".json", **{"data/config": '{"key": "value"}'})
        pytester.makefile(".txt", **{"data/data1": "a\nb"})
        pytester.makefile(".txt", **{"data/data2": "a\nb"})
        pytester.makepyfile(f"""
        import pytest
        {import_code}

        @pytest.mark.parametrize("p1", [1,2])
        @load("cfg", "config.json")
        @parametrize('data1', 'data1.txt')
        {erring_data_loader_def}
        @parametrize('data2', 'data2.txt')
        @pytest.mark.parametrize("p2", [3,4])
        def test_func(cfg, missing, data1, data2, p1, p2):
            pass
        """)
        result = pytester.runpytest("--collect-only", "-q")
        assert result.ret == ExitCode.INTERRUPTED
        output = str(result.stdout)
        assert f"data loader: {erring_data_loader_def}" in output
        assert output.count("@parametrize") == 1
        assert "@load" not in output
