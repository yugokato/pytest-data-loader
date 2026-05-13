from pathlib import Path

import pytest
from _pytest.config import ExitCode
from pytest import Pytester

from pytest_data_loader.types import DataLoaderIniOption, DataLoaderOnMissingAction

pytestmark = pytest.mark.plugin


@pytest.fixture(autouse=True)
def data_dir(pytester: Pytester) -> Path:
    return pytester.mkdir("data")


class TestParametrizeLoaderFuncGlobalIdx:
    """Tests for idx arg support in @parametrize loader callable options"""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("file_extension", [".txt", ".json"])
    def test_idx_with_processor_func(
        self, pytester: Pytester, data_dir: Path, lazy_loading: bool, file_extension: str
    ) -> None:
        """Test that @parametrize processor receives sequential post-filter idx.

        processor replaces each item with its idx. The test asserts that the received idx equals
        the pytest callspec index, which confirms post-filter sequential numbering (0, 1, 2, ...).
        """
        if file_extension == ".txt":
            (data_dir / "file.txt").write_text("line0\nline1\nline2\nline3\nline4\n")
            filter_def = "lambda d: int(d[-1]) % 2"
        else:
            (data_dir / "file.json").write_text('{"k0": "v0", "k1": "v1", "k2": "v2", "k3": "v3", "k4": "v4"}')
            filter_def = "lambda d: int(d[0][-1]) % 2"
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            "file{file_extension}",
            lazy_loading={lazy_loading},
            filter={filter_def},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            # processor replaced the original data with idx; callspec index equals post-filter idx
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_marks_func(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize marks callable correctly uses post-filter idx to skip the right item.

        After filtering, 3 items remain (post-filter idx 0, 1, 2). marks skips idx==1 (middle item).
        The test verifies exactly 1 skip and 2 passes.
        """
        # 5 lines; filter keeps line1, line2, line3 → post-filter idx: 0, 1, 2
        idx_to_skip = 1
        (data_dir / "file.txt").write_text("line0\nline1\nline2\nline3\nline4\n")
        pytester.makepyfile(f"""
        import pytest
        from pytest_data_loader import parametrize

        data_to_test = ("line1", "line2", "line3")

        @parametrize(
            "data",
            "file.txt",
            lazy_loading={lazy_loading},
            filter=lambda d: d in data_to_test,
            marks=lambda i, p, d: pytest.mark.skip if i == {idx_to_skip} else None
        )
        def test_func(data):
            assert data != data_to_test[{idx_to_skip}]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2, skipped=1)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize("file_extension", [".txt", ".json"])
    def test_idx_with_ids_func(
        self, pytester: Pytester, data_dir: Path, lazy_loading: bool, file_extension: str
    ) -> None:
        """Test that @parametrize ids receives sequential post-filter global idx regardless of which items were
        filtered out.

        The file has 5 items but only 2 pass the filter. If idx were pre-filter positions, the ids would be
        "item-1" and "item-3". If post-filter, they should be "item-0" and "item-1".
        """
        if file_extension == ".txt":
            (data_dir / "file.txt").write_text("line0\nline1\nline2\nline3\nline4\n")
            filter_def = "lambda d: int(d[-1]) % 2"
        else:
            (data_dir / "file.json").write_text('{"k0": "v0", "k1": "v1", "k2": "v2", "k3": "v3", "k4": "v4"}')
            filter_def = "lambda d: int(d[0][-1]) % 2"
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            "file{file_extension}",
            lazy_loading={lazy_loading},
            filter={filter_def},
            ids=lambda i, p, d: f"item-{{i}}"
        )
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)
        output = str(result.stdout)
        assert "[item-0]" in output
        assert "[item-1]" in output
        assert "[item-2]" not in output

    def test_idx_non_streamable_lazy(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that non-streamable lazy @parametrize passes correct post-filter idx to all callables.

        Uses a .yaml file with parametrizer, filter, processor, marks, and ids all relying on idx. With filter keeping
        items at positions 1 and 3 (0-indexed),
        post-filter idx must be 0 and 1 for all callables regardless of how many times _load_now runs
        internally.

        Asserts:
        - processor is called exactly N times (not 2N or 3N — no double-invocation)
        - each test receives the data produced by processor(post_filter_idx, path, raw)
        - marks callable receives the correct post-filter idx (idx=1 is skipped)
        - ids callable receives the correct post-filter idx
        """
        (data_dir / "file.yaml").write_text("item0\nitem1\nitem2\nitem3\n")
        pytester.makepyfile("""
        import pytest
        from pytest_data_loader import parametrize

        processor_calls: list[int] = []
        marker_calls: list[int] = []

        @parametrize(
            "data",
            "file.yaml",
            lazy_loading=True,
            parametrizer=lambda d: [line for line in d.splitlines() if line],
            filter=lambda d: int(d[-1]) % 2,
            processor=lambda i, p, d: (processor_calls.append(i), i)[1],
            marks=lambda i, p, d: (marker_calls.append(i), pytest.mark.skip if i == 1 else None)[1],
            ids=lambda i, p, d: f"item-{i}",
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]

        def test_verify_call_counts():
            # marks is called once per post-filter item at collection time
            assert marker_calls == [0, 1]
            # processor is called at test-time only for non-skipped items.
            # item-1 is skipped by marks so only item-0 triggers processor with idx=0.
            assert processor_calls == [0]
        """)
        result = pytester.runpytest("-v")
        # test_func[item-0] passes, test_func[item-1] is skipped, test_verify_call_counts passes
        result.assert_outcomes(passed=2, skipped=1)
        output = str(result.stdout)
        assert "[item-0]" in output
        assert "[item-1]" in output


class TestParametrizeDirLoaderFuncGlobalIdx:
    """Tests for idx arg support in @parametrize_dir loader function callbacks.

    The test directory has 4 files sorted alphabetically: file0.txt, file1.txt, file2.txt, file3.txt.
    The filter keeps file1.txt and file3.txt. Post-filter idx: 0 → file1.txt, 1 → file3.txt.
    """

    def test_idx_with_reader_func(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that @parametrize_dir reader callable receives sequential post-filter idx.

        The reader embeds the received idx into the returned data. If idx were pre-filter (1 and 3
        for file1 and file3), the embedded values would not match the pytest callspec indices (0, 1).
        """
        dir_path = data_dir / "dir"
        dir_path.mkdir()
        for i in range(4):
            (dir_path / f"file{i}.txt").write_text(f"content{i}")
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            "dir",
            filter=lambda p: p.name in ("file1.txt", "file3.txt"),
            reader=lambda i, p: (lambda f, i=i: f.read().rstrip() + f"-{i}"),
            ids=lambda i, p: f"item-{i}"
        )
        def test_func(request, data):
            # data is "contentN-M" where M is the idx passed by reader
            idx_in_data = int(data.split("-")[-1])
            assert idx_in_data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)
        output = str(result.stdout)
        assert "[item-0]" in output
        assert "[item-1]" in output

    def test_idx_with_read_options_func(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that @parametrize_dir read_options callable receives sequential post-filter idx.

        A module-level list captures the idx values at collection time. A verification test asserts
        they are [0, 1] (post-filter). If pre-filter, they would be [1, 3].
        """
        dir_path = data_dir / "dir"
        dir_path.mkdir()
        for i in range(4):
            (dir_path / f"file{i}.txt").write_text(f"content{i}")
        pytester.makepyfile("""
        from pytest_data_loader import parametrize_dir

        captured_indices: list[int] = []

        @parametrize_dir(
            "data",
            "dir",
            filter=lambda p: p.name in ("file1.txt", "file3.txt"),
            read_options=lambda i, p: (captured_indices.append(i), {})[1],
            ids=lambda i, p: f"item-{i}"
        )
        def test_with_read_options(data):
            pass

        def test_verify_captured_indices():
            assert sorted(captured_indices) == [0, 1]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=3)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_processor_func(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize_dir processor receives sequential post-filter idx per directory."""
        dir_path = data_dir / "dir"
        dir_path.mkdir()
        for i in range(4):
            (dir_path / f"file{i}.txt").write_text(f"content{i}")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            "dir",
            lazy_loading={lazy_loading},
            filter=lambda p: p.name in ("file1.txt", "file3.txt"),
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_marks_func(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize_dir marks callable correctly uses post-filter idx to skip the right item."""
        dir_path = data_dir / "dir"
        dir_path.mkdir()
        for i in range(4):
            (dir_path / f"file{i}.txt").write_text(f"content{i}")
        # Filter keeps file1.txt (idx=0) and file3.txt (idx=1). marks skips idx==0.
        pytester.makepyfile(f"""
        import pytest
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            "dir",
            lazy_loading={lazy_loading},
            filter=lambda p: p.name in ("file1.txt", "file3.txt"),
            marks=lambda i, p: pytest.mark.skip if i == 0 else None
        )
        def test_func(data):
            pass
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=1, skipped=1)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_ids_func(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize_dir ids receives sequential post-filter idx.

        With 4 files and a filter keeping file1 and file3, ids should be "item-0" and "item-1",
        not "item-1" and "item-3" (which would be pre-filter positions).
        """
        dir_path = data_dir / "dir"
        dir_path.mkdir()
        for i in range(4):
            (dir_path / f"file{i}.txt").write_text(f"content{i}")
        pytester.makepyfile(f"""
            from pytest_data_loader import parametrize_dir

            @parametrize_dir(
                "data",
                "dir",
                lazy_loading={lazy_loading},
                filter=lambda p: p.name in ("file1.txt", "file3.txt"),
                ids=lambda i, p: f"item-{{i}}"
            )
            def test_func(data):
                pass
            """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)
        output = str(result.stdout)
        assert "[item-0]" in output
        assert "[item-1]" in output
        assert "[item-2]" not in output


class TestGlobalIdxInMultiPaths:
    """Tests that a global idx is continuous across all paths matched by a single decorator invocation."""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_multi_paths_parametrize(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize with a tuple of paths produces continuous idx across both files.

        Two files with 2 lines each. processor replaces data with its idx. The test asserts
        data == callspec index, confirming idx is 0, 1, 2, 3 (not 0, 1, 0, 1).
        """
        (data_dir / "a.txt").write_text("a0\na1\n")
        (data_dir / "b.txt").write_text("b0\nb1\n")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            ("a.txt", "b.txt"),
            lazy_loading={lazy_loading},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_glob_path_parametrize(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize with a glob produces continuous idx across all matched files.

        Three files with 2 lines each (6 items total). processor replaces data with idx.
        The test asserts data == callspec index, confirming idx runs 0..5.
        """
        for i in range(3):
            (data_dir / f"file{i}.txt").write_text(f"line{i}a\nline{i}b\n")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            "*.txt",
            lazy_loading={lazy_loading},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=6)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_multi_paths_parametrize_dir(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize_dir with a tuple of directories produces continuous idx.

        Two directories with 2 files each. processor replaces data with idx.
        The test asserts data == callspec index, confirming idx is 0, 1, 2, 3.
        """
        for d in ("dir1", "dir2"):
            dir_path = data_dir / d
            dir_path.mkdir()
            for i in range(2):
                (dir_path / f"file{i}.txt").write_text(f"{d}-content{i}")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            ("dir1", "dir2"),
            lazy_loading={lazy_loading},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_glob_path_parametrize_dir(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that @parametrize_dir with a glob produces continuous idx across all matched directories.

        Two directories with 2 files each. processor replaces data with idx.
        Confirms idx runs 0..3, not 0..1 twice.
        """
        dirs_root = data_dir / "dirs"
        dirs_root.mkdir()
        for i in range(2):
            d = dirs_root / f"sub{i}"
            d.mkdir()
            for j in range(2):
                (d / f"file{j}.txt").write_text(f"sub{i}-content{j}")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            "dirs/*",
            lazy_loading={lazy_loading},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=4)

    def test_idx_with_stacked_data_loaders(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that stacked data loaders each have their own independent idx counter.

        Each axis has 2 files with 1 line each. processor replaces data with idx.
        Each axis must see idx values [0, 1] independently — not continuing from the other.
        """
        for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
            (data_dir / name).write_text(f"line-{name}\n")
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize("x", ("a.txt", "b.txt"), processor=lambda i, p, d: i)
        @parametrize("y", ("c.txt", "d.txt"), processor=lambda i, p, d: i)
        def test_func(request, x, y):
            # Each axis independently produces idx 0 and 1
            assert x in (0, 1)
            assert y in (0, 1)
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=4)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_with_empty_dir(self, pytester: Pytester, data_dir: Path, lazy_loading: bool) -> None:
        """Test that an empty directory in multi paths does not consume idx values.

        Two directories: empty_dir (0 files) and full_dir (2 files).
        idx must start at 0 in full_dir, not shifted by a phantom draw from empty_dir.
        """
        (data_dir / "empty_dir").mkdir()
        full = data_dir / "full_dir"
        full.mkdir()
        for i in range(2):
            (full / f"file{i}.txt").write_text(f"content{i}")
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize_dir

        @parametrize_dir(
            "data",
            ("empty_dir", "full_dir"),
            lazy_loading={lazy_loading},
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=2)

    def test_idx_continuous_across_files_with_strip_trailing_whitespace(
        self, pytester: Pytester, data_dir: Path
    ) -> None:
        """Test that trailing blank lines in a file do not consume idx values for subsequent files.

        File A has 2 real lines followed by 2 blank lines (strip_trailing_whitespace drops them).
        File B has 3 lines. If trailing-blank lines consumed idx, B's items would receive idx 4, 5, 6
        instead of the correct 2, 3, 4. processor replaces data with its idx; the test asserts
        data == callspec index, which fails when there are gaps.
        """
        pytester.makeini("""
        [pytest]
        data_loader_strip_trailing_whitespace = true
        """)
        (data_dir / "a.txt").write_text("a0\na1\n\n\n")
        (data_dir / "b.txt").write_text("b0\nb1\nb2\n")
        pytester.makepyfile("""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            ("a.txt", "b.txt"),
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            # If trailing blanks leaked idx, file B items would have idx 4,5,6 not 2,3,4
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=5)

    @pytest.mark.parametrize("lazy_loading", [True, False])
    def test_idx_continuous_with_filter_across_glob_files(
        self, pytester: Pytester, data_dir: Path, lazy_loading: bool
    ) -> None:
        """Test that idx is continuous across glob-matched files when filter drops items from each.

        Two .json files, each with 4 items. filter keeps only odd-indexed items from each file
        (items at raw positions 1 and 3). Post-filter idx across both files must be 0, 1, 2, 3.
        processor replaces data with idx; the test asserts data == callspec index.
        """
        for name in ("file1.json", "file2.json"):
            (data_dir / name).write_text('{"k0": "v0", "k1": "v1", "k2": "v2", "k3": "v3"}')
        pytester.makepyfile(f"""
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            "*.json",
            lazy_loading={lazy_loading},
            filter=lambda d: int(d[0][-1]) % 2,
            processor=lambda i, p, d: i
        )
        def test_func(request, data):
            # 2 files x 2 kept items each = 4 total, idx must be 0,1,2,3
            assert data == request.node.callspec.indices["data"]
        """)
        result = pytester.runpytest("-v")
        result.assert_outcomes(passed=4)


class TestGlobalIdxOnMissingData:
    """Tests global idx when missing data"""

    @pytest.mark.parametrize("lazy_loading", [True, False])
    @pytest.mark.parametrize(
        "on_missing",
        [DataLoaderOnMissingAction.SKIP, DataLoaderOnMissingAction.XFAIL, DataLoaderOnMissingAction.WARN],
    )
    def test_missing_data_does_not_consume_global_idx(
        self, pytester: pytest.Pytester, data_dir: Path, on_missing: DataLoaderOnMissingAction, lazy_loading: bool
    ) -> None:
        """Test that missing data does not consume the global idx"""
        (data_dir / "first.txt").write_text("line1\nline2")
        (data_dir / "third.txt").write_text("line1\nline2")
        pytester.makeini(f"""
        [pytest]
        {DataLoaderIniOption.DATA_LOADER_ON_MISSING} = {on_missing.value}
        """)
        pytester.makepyfile(f"""
        import pytest
        from pytest_data_loader import parametrize

        @parametrize(
            "data",
            ["first.txt", "second_missing.txt", "third.txt"],
            lazy_loading={lazy_loading},
            processor=lambda i, *_: i,
            marks=lambda i, *_: getattr(pytest.mark, f"mark{{i}}"),
            ids=lambda i, p, d: "item" + str(i),
        )
        def test_func(request, data):
            call_idx = request.node.callspec.indices["data"]
            if call_idx < 2:
                assert data == call_idx
                assert request.node.get_closest_marker(f"mark{{call_idx}}")
            elif call_idx == 2:
                # missing data
                assert data is None
            else:
                assert data == call_idx-1
                assert request.node.get_closest_marker(f"mark{{call_idx-1}}")
        """)
        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        output = str(result.stdout)
        assert all(x in output for x in ("item0", "item1", "item2", "item3"))
        assert "item4" not in output
