import re
import sys
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

pytestmark = pytest.mark.plugin


@pytest.fixture(autouse=True)
def data_dir(pytester: Pytester) -> Path:
    return pytester.mkdir("data")


class TestParametrizeWithGlobPath:
    """Tests for glob pattern support in @parametrize."""

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_single_wildcard(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a *.ext pattern loads all matching files and concatenates their parts."""
        _create_files(data_dir, ["a.txt", "b.txt", "c.log"])

        pattern = "*.txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            assert file_path.suffix == ".txt"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_literal_prefix(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a pattern with a literal prefix directory (xyz/*.ext) resolves correctly."""
        sub_dir = "dir"
        _create_files(data_dir, ["a.txt", "b.txt"])
        _create_files(data_dir, ["c.txt", "d.txt", "e.log"], sub_dir=sub_dir)

        pattern = f"{sub_dir}/*.txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pathlib import Path
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            assert file_path.is_relative_to(Path({str(data_dir / sub_dir)!r}))
            assert file_path.suffix == ".txt"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("match_files", [True, False])
    def test_glob_with_globstar(self, pytester: Pytester, data_dir: Path, is_abs: bool, match_files: bool) -> None:
        """Test that a ** pattern matches files in nested subdirectories."""
        sub_dir = "dir"
        nested_dir1 = data_dir / sub_dir / "nested1"
        nested_dir2 = data_dir / sub_dir / "nested2" / "nested3"
        _create_files(data_dir, ["a.txt", "b.txt", "x.log"], sub_dir=nested_dir1)
        _create_files(data_dir, ["c.txt", "d.txt", "y.log"], sub_dir=nested_dir2)

        pattern = f"{sub_dir}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        if match_files:
            pattern += "/*.txt"

        code = f"""
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            ...
        """
        if match_files:
            code += '    assert file_path.suffix == ".txt"\n'
        pytester.makepyfile(code)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4 if match_files else 6)

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("is_negation", [False, True])
    def test_glob_with_character_set(self, pytester: Pytester, data_dir: Path, is_abs: bool, is_negation: bool) -> None:
        """Test that a xyz[...].ext pattern loads all matching files and concatenates their parts."""
        _create_files(data_dir, ["a.txt", "b.txt", "c.txt", "d.log"])

        if is_negation:
            pattern = "[!ab].txt"
        else:
            pattern = "[ab].txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            assert file_path.suffix == ".txt"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1 if is_negation else 2)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_literal_path(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a list mixing a glob and a literal path aggregates in order."""
        sub_dir = "dir"
        _create_files(data_dir, ["a.txt"])
        _create_files(data_dir, ["b.txt", "c.txt", "d.log"], sub_dir=sub_dir)

        pattern = f"{sub_dir}/*.txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), ["a.txt", {pattern!r}])
        def test_func(file_path, data):
            ...
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("is_base_dir_hidden", [False, True])
    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_excludes_hidden_files(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, is_base_dir_hidden: bool
    ) -> None:
        """Test that hidden files and directories (starting with '.') are excluded from matching paths, except for the
        base directory of the pattern.
        """
        sub_dir = "dir"
        if is_base_dir_hidden:
            sub_dir = f".{sub_dir}"
        nested_dir_visible = data_dir / sub_dir / "nested"
        nested_dir_hidden = data_dir / sub_dir / ".nested_hidden"
        _create_files(data_dir, ["visible1.txt", ".hidden1.txt"], sub_dir=sub_dir)
        _create_files(data_dir, ["visible2.txt", ".hidden2.txt"], sub_dir=nested_dir_visible)
        _create_files(data_dir, ["should_be_excluded.txt", ".hidden3.txt"], sub_dir=nested_dir_hidden)

        pattern = f"{sub_dir}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
            from pytest_data_loader import parametrize

            @parametrize(("file_path", "data"), {pattern!r})
            def test_func(file_path, data):
                assert not file_path.name.startswith(".")
                assert file_path.name != "should_be_excluded.txt"
            """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_no_matching_file(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a glob matching no files raises FileNotFoundError"""
        pattern = "foo/*.txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize("data", {pattern!r})
        def test_func(data):
            ...
        """)
        result = pytester.runpytest("--collect-only")
        assert result.ret == ExitCode.INTERRUPTED
        result.stdout.fnmatch_lines(["*FileNotFoundError: Glob pattern*matched no files*"])

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("has_matching_file", [True, False])
    def test_glob_pattern_is_checked_as_literal_file_path_first(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, has_matching_file: bool
    ) -> None:
        """Test that a glob pattern that matches actual file name is treated as a literal path"""
        files = ["file1.txt", "file2.txt"]
        if has_matching_file:
            files.append("file[12].txt")
        _create_files(data_dir, files)

        pattern = "file[12].txt"
        if is_abs:
            pattern = str(data_dir / pattern)

        code = f"""
        from pytest_data_loader import parametrize

        @parametrize(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
        """
        if has_matching_file:
            code += '    assert "[" in file_path.name\n'
        else:
            code += '    assert "[" not in file_path.name\n'

        pytester.makepyfile(code)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1 if has_matching_file else 2)


class TestParametrizeDirWithGlobPath:
    """Tests for glob pattern support in @parametrize_dir."""

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_single_wildcard(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a foo*bar pattern loads each matched directory files as a separate test case."""
        sub_dir1 = "dir1"
        sub_dir2 = "dir2"
        _create_files(data_dir, ["a.txt", "b.txt"], sub_dir=sub_dir1)
        _create_files(data_dir, ["c.txt", "d.txt"], sub_dir=sub_dir2)

        pattern = "dir*"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            ...
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_globstar(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a ** pattern matches files in nested subdirectories."""
        sub_dir = "dir"
        nested_dir1 = data_dir / sub_dir / "nested1"
        nested_dir2 = data_dir / sub_dir / "nested2" / "nested3"
        _create_files(data_dir, ["a.txt", "b.txt"], sub_dir=nested_dir1)
        _create_files(data_dir, ["c.txt"], sub_dir=nested_dir2)

        pattern = f"{sub_dir}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            ...
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("is_negation", [False, True])
    def test_glob_with_character_set(self, pytester: Pytester, data_dir: Path, is_abs: bool, is_negation: bool) -> None:
        """Test that a xyz[...] pattern loads each matched directory files as a separate test case."""
        sub_dir1 = "dir1"
        sub_dir2 = "dir2"
        sub_dir3 = "dir3"
        _create_files(data_dir, ["a.txt"], sub_dir=sub_dir1)
        _create_files(data_dir, ["b.txt", "c.txt"], sub_dir=sub_dir2)
        _create_files(data_dir, ["d.txt", "e.txt", "f.txt"], sub_dir=sub_dir3)

        if is_negation:
            pattern = "dir[!13]"
        else:
            pattern = "dir[13]"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            ...
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2 if is_negation else 4)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_literal_path(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a list mixing a glob and a literal path aggregates in order."""
        sub_dir1 = "dir1"
        sub_dir2 = "dir2"
        _create_files(data_dir, ["a.txt"], sub_dir=sub_dir1)
        _create_files(data_dir, ["b.txt", "c.txt", "d.log"], sub_dir=sub_dir2)

        pattern = f"{sub_dir2}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
           from pytest_data_loader import parametrize_dir

           @parametrize_dir(("file_path", "data"), [{sub_dir1!r}, {pattern!r}])
           def test_func(file_path, data):
               ...
           """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_with_no_matching_dir(self, pytester: Pytester, data_dir: Path, is_abs: bool) -> None:
        """Test that a glob matching no directories raises FileNotFoundError"""
        pattern = "foo/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", {pattern!r})
        def test_func(data):
            ...
        """)
        result = pytester.runpytest("--collect-only")
        assert result.ret == ExitCode.INTERRUPTED
        result.stdout.fnmatch_lines(["*FileNotFoundError: Glob pattern*matched no directories*"])

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("collect_only", [True, False])
    def test_glob_with_no_matching_dir_files(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, collect_only: bool
    ) -> None:
        """Test that a glob matching directory with no file is handled gracefully"""
        sub_dir = "dir"
        _create_files(data_dir, [], sub_dir=sub_dir)

        pattern = f"{sub_dir}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir("data", {pattern!r})
        def test_func(data):
            ...
        """)
        args = []
        if collect_only:
            args.append("--collect-only")
        result = pytester.runpytest(*args)
        assert result.ret == ExitCode.OK
        if collect_only:
            if pytest.version_tuple >= (8, 4):
                assert "NOTSET" in str(result.stdout)
        else:
            result.assert_outcomes(skipped=1)

    @pytest.mark.parametrize("is_abs", [True, False])
    @pytest.mark.parametrize("has_matching_dir", [True, False])
    def test_glob_pattern_is_checked_as_literal_dir_path_first(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, has_matching_dir: bool
    ) -> None:
        """Test that a glob pattern that matches actual directory name is treated as a literal path"""
        sub_dir1 = "dir1"
        sub_dir2 = "dir2"
        _create_files(data_dir, ["a.txt"], sub_dir=sub_dir1)
        _create_files(data_dir, ["b.txt"], sub_dir=sub_dir2)
        if has_matching_dir:
            _create_files(data_dir, ["c.txt"], sub_dir="dir[12]")

        pattern = "dir[12]"
        if is_abs:
            pattern = str(data_dir / pattern)

        code = f"""
            from pytest_data_loader import parametrize_dir

            @parametrize_dir(("file_path", "data"), {pattern!r})
            def test_func(file_path, data):
            """
        if has_matching_dir:
            code += '    assert "[" in file_path.parent.name\n'
        else:
            code += '    assert "[" not in file_path.parent.name\n'

        pytester.makepyfile(code)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1 if has_matching_dir else 2)

    @pytest.mark.parametrize("is_base_dir_hidden", [False, True])
    @pytest.mark.parametrize("is_abs", [True, False])
    def test_glob_excludes_hidden_dirs(
        self, pytester: Pytester, data_dir: Path, is_abs: bool, is_base_dir_hidden: bool
    ) -> None:
        """Test that hidden directories (starting with '.') are excluded from matching paths, except for the base
        directory of the pattern.
        """
        sub_dir = "dir"
        if is_base_dir_hidden:
            sub_dir = f".{sub_dir}"
        nested_dir_visible = data_dir / sub_dir / "nested"
        nested_dir_hidden = data_dir / sub_dir / ".nested_hidden"
        _create_files(data_dir, ["visible1.txt", ".hidden1.txt"], sub_dir=sub_dir)
        _create_files(data_dir, ["visible2.txt", ".hidden2.txt"], sub_dir=nested_dir_visible)
        _create_files(data_dir, ["should_be_excluded.txt", ".hidden3.txt"], sub_dir=nested_dir_hidden)

        pattern = f"{sub_dir}/**"
        if is_abs:
            pattern = str(data_dir / pattern)

        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(("file_path", "data"), {pattern!r})
        def test_func(file_path, data):
            assert not file_path.name.startswith(".")
            assert file_path.name != "should_be_excluded.txt"
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("has_globstar", [True, False])
    @pytest.mark.parametrize("with_literal_path", [True, False])
    def test_glob_without_globstar_ignores_recursive_option_with_warning(
        self, pytester: Pytester, data_dir: Path, has_globstar: bool, with_literal_path: bool
    ) -> None:
        """Test that recursive option is ignored for glob pattern paths, and a warning message is logged if the
        pattern doesn't contain a globstar.
        The option should still work with literal paths if both are mixed.
        """
        glob_dir = "glob_dir"
        literal_dir = "literal_dir"
        glob_dir_nested = data_dir / glob_dir / "nested"
        literal_dir_nested = data_dir / literal_dir / "nested"
        _create_files(data_dir, ["a.txt"], sub_dir=glob_dir)
        _create_files(data_dir, ["b.txt"], sub_dir=glob_dir_nested)
        _create_files(data_dir, ["c.txt"], sub_dir=literal_dir)
        _create_files(data_dir, ["d.txt"], sub_dir=literal_dir_nested)

        if has_globstar:
            pattern = f"{glob_dir}/**"
            num_tests = 4 if with_literal_path else 2
        else:
            pattern = f"{glob_dir}/*"
            num_tests = 3 if with_literal_path else 1

        if with_literal_path:
            path = f"[{pattern!r}, {literal_dir!r}]"
        else:
            path = f"{pattern!r}"

        loader_def = f'@parametrize_dir(("file_path", "data"), {path}, recursive=True)'
        p = pytester.makepyfile(f"""
                from pytest_data_loader import parametrize_dir

                {loader_def}
                def test_func(file_path, data):
                    ...
                """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=num_tests)
        if has_globstar:
            assert "UserWarning" not in str(result.stdout)
        else:
            # On Windows, !r formatting renders the backslash separator as '\\', so match either form.
            pattern_regex = re.escape(pattern).replace("/", r"(?:\\\\|/)")
            result.stdout.re_match_lines(
                [
                    (
                        rf"\s+{re.escape(str(p))}:\d: UserWarning: The 'recursive' option is ignored for the glob "
                        rf"pattern '{pattern_regex}'\. Use '\*\*' in the pattern to enable recursive matching"
                    ),
                    rf"\s+{re.escape(loader_def)}" if sys.version_info >= (3, 11) else r"\s+def test_func.+",
                ],
                consecutive=True,
            )


class TestGlobPathUnsupportedCases:
    """Tests for unsupported scenarios around glob patterns"""

    def test_glob_with_load_unsupported(self, pytester: Pytester) -> None:
        """Test that @load raises an error when given a glob pattern."""
        pytester.makepyfile("""
        from pytest_data_loader import load

        @load("data", "dir/*.txt")
        def test_func(data):
            ...
        """)
        result = pytester.runpytest("--collect-only")
        assert result.ret == ExitCode.INTERRUPTED
        assert "@load loader does not support glob pattern" in str(result.stdout)


def _create_files(data_dir: Path, file_names: list[str], sub_dir: Path | str | None = None) -> Path:
    if sub_dir:
        dir_path = data_dir / sub_dir
        dir_path.mkdir(parents=True, exist_ok=True)
    else:
        dir_path = data_dir
    for file_name in file_names:
        (dir_path / file_name).write_text("line\n")
    return dir_path
