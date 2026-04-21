import inspect
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _pytest.pytester import Pytester
from pytest import RunResult

from pytest_data_loader import parametrize
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.types import DataLoader, DataLoaderFunctionType
from pytest_data_loader.utils import is_valid_fixture_name


@dataclass(kw_only=True)
class TestContext:
    """Container for the per-test pytester context created by the ``test_context`` fixture."""

    __test__ = False

    pytester: Pytester
    loader: DataLoader
    data_dir: Path | str
    path: Path | str
    test_file_ext: str
    test_file_content: str | bytes
    strip_trailing_whitespace: bool = True

    @property
    def num_expected_tests(self) -> int:
        """Number of inner test cases expected to be parametrized from the test data."""
        if self.loader.is_file_loader:
            if self.loader.requires_parametrization:
                if self.test_file_ext == ".json":
                    num_expected_tests = len(json.loads(self.test_file_content).items())
                elif self.test_file_ext == ".jsonl":
                    assert isinstance(self.test_file_content, str)
                    num_expected_tests = sum(1 for line in self.test_file_content.splitlines() if line.strip())
                elif self.test_file_ext == ".txt":
                    assert isinstance(self.test_file_content, str)
                    if self.strip_trailing_whitespace:
                        num_expected_tests = len(self.test_file_content.rstrip().splitlines())
                    else:
                        num_expected_tests = len(self.test_file_content.rstrip("\r\n").splitlines())
                elif self.test_file_ext == ".png":
                    num_expected_tests = 1
                else:
                    raise NotImplementedError(f"Not supported for {self.test_file_ext} file")
            else:
                num_expected_tests = 1
        else:
            num_expected_tests = len(list(Path(self.data_dir, self.path).resolve().iterdir()))
        return num_expected_tests


@dataclass
class LoaderRootDir:
    """Configuration for an optional loader root directory."""

    requested_path: str | None = None
    resolved_path: Path | None = None


def is_valid_fixture_names(args: str | tuple[str, ...]) -> bool:
    """Return True if ``args`` represents one or two valid Python identifiers as fixture names.

    :param args: A comma-separated string or tuple of fixture name strings.
    """
    if isinstance(args, str):
        args = tuple(x.strip() for x in args.split(","))
    else:
        args = tuple(args)
    return 0 < len(args) < 3 and all(is_valid_fixture_name(x) for x in args)


def get_num_func_args(loader_func: Callable[..., Any]) -> int:
    """Return the number of positional parameters accepted by ``loader_func``.

    :param loader_func: The callable to inspect.
    """
    sig = inspect.signature(loader_func)
    return len(sig.parameters)


def create_test_data_in_data_dir(
    pytester: Pytester,
    data_dir: Path | str,
    relative_file_path: Path | str,
    loader_root_dir: Path | None = None,
    data: str | bytes = "content",
    return_abs_path: bool = False,
) -> Path:
    """Create a test data file inside the pytester data directory.

    :param pytester: The pytester fixture.
    :param data_dir: Name or path of the data directory relative to the pytester root.
    :param relative_file_path: Path of the file relative to ``data_dir``.
    :param loader_root_dir: Optional absolute path to an alternative loader root directory.
    :param data: File content (str or bytes).
    :param return_abs_path: When True, return the absolute path instead of the relative one.
    """
    if loader_root_dir:
        data_dir = loader_root_dir / data_dir
    else:
        data_dir = Path(data_dir)

    abs_file_path = (data_dir / relative_file_path).resolve()
    if not abs_file_path.parent.exists():
        abs_file_path.parent.mkdir(parents=True, exist_ok=True)
    name, ext = os.path.splitext(abs_file_path)
    if ext == ".png":
        assert isinstance(data, bytes), "PNG files require bytes content"
        abs_file_path.write_bytes(data)
    else:
        pytester.makefile(ext, **{name: data})
    assert abs_file_path.exists()

    if return_abs_path:
        return abs_file_path
    return Path(relative_file_path)


def create_test_context(
    pytester: Pytester,
    loader: DataLoader,
    /,
    *,
    file_extension: str = ".txt",
    file_content: str | bytes = "foo\nbar",
    parent_dirs: Path | str = "",  # dir(s) under the loader dir
    data_dir_name: str = DEFAULT_LOADER_DIR_NAME,
    loader_root_dir: LoaderRootDir = LoaderRootDir(),
    strip_trailing_whitespace: bool = True,
    path_type: type[str | Path] = str,
    is_abs_path: bool = False,
) -> TestContext:
    """Create a :class:`TestContext` with the necessary test data files for a pytester run.

    :param pytester: The pytester fixture.
    :param loader: The loader decorator under test.
    :param file_extension: Extension of the test data file(s).
    :param file_content: Content written into the test data file(s).
    :param parent_dirs: Optional subdirectory path under the data dir.
    :param data_dir_name: Name of the data directory searched by the plugin.
    :param loader_root_dir: Optional custom loader root directory configuration.
    :param strip_trailing_whitespace: Forwarded to :class:`TestContext` for line-count calculations.
    :param path_type: Python type (``str`` or ``Path``) used for the path argument in the inner test.
    :param is_abs_path: When True the path argument is absolute.
    """
    test_data_dir = pytester.mkdir(data_dir_name)
    if parent_dirs:
        Path(test_data_dir, parent_dirs).mkdir(parents=True, exist_ok=True)
    if loader.is_file_loader:
        path = create_test_data_in_data_dir(
            pytester,
            data_dir_name,
            Path(parent_dirs, f"file{file_extension}"),
            loader_root_dir=loader_root_dir.resolved_path,
            data=file_content,
            return_abs_path=is_abs_path,
        )
    else:
        path = Path(parent_dirs, "dir")
        paths = {
            create_test_data_in_data_dir(
                pytester,
                data_dir_name,
                path / f"file{i}{file_extension}",
                loader_root_dir=loader_root_dir.resolved_path,
                data=file_content,
                return_abs_path=is_abs_path,
            ).parent
            for i in range(2)
        }
        assert len(paths) == 1
        if is_abs_path:
            path = paths.pop().resolve()

    if is_abs_path:
        assert path.is_absolute()
    else:
        assert not path.is_absolute()

    return TestContext(
        pytester=pytester,
        loader=loader,
        data_dir=test_data_dir,
        path=path_type(path),
        test_file_ext=file_extension,
        test_file_content=file_content,
        strip_trailing_whitespace=strip_trailing_whitespace,
    )


def run_pytest_with_context(
    test_context: TestContext,
    fixture_names: str | tuple[str, ...] = ("arg1", "arg2"),
    data_loader_root_dir: Path | None = None,
    path: Path | str | None = None,
    lazy_loading: bool | None = True,
    onload_func_def: str | None = None,
    parametrizer_func_def: str | None = None,
    filter_func_def: str | None = None,
    process_func_def: str | None = None,
    marker_func_def: str | None = None,
    id_: str | None = None,
    id_func_def: str | None = None,
    file_reader_func_def: str | None = None,
    read_option_func_def: str | None = None,
    collect_only: bool = False,
    check_test_id: bool = False,
    **other_loader_options: Any,
) -> RunResult:
    """Run pytest via pytester with the given test context and loader options.

    Builds an inner test module that exercises the plugin under the conditions defined by
    ``test_context`` and the loader arguments, runs it, and returns the result.

    :param test_context: The test context containing pytester, loader, path, and file-content metadata.
    :param fixture_names: Fixture name(s) to pass to the decorator.
    :param data_loader_root_dir: When set, asserts the resolved file paths are under this directory.
    :param path: Override the path from ``test_context``.
    :param lazy_loading: ``None`` uses the loader default; ``False`` forces eager loading.
    :param onload_func_def: Python expression string for the ``onload_func`` argument.
    :param parametrizer_func_def: Python expression string for the ``parametrizer_func`` argument.
    :param filter_func_def: Python expression string for the ``filter_func`` argument.
    :param process_func_def: Python expression string for the ``process_func`` argument.
    :param marker_func_def: Python expression string for the ``marker_func`` argument.
    :param id_: Explicit id string for the ``@load`` decorator.
    :param id_func_def: Python expression string for the ``id_func`` argument.
    :param file_reader_func_def: Python expression string for the ``file_reader_func`` argument.
    :param read_option_func_def: Python expression string for the ``read_option_func`` argument.
    :param collect_only: When True run with ``--collect-only`` instead of ``-vs``.
    :param check_test_id: When True, append assertions about the pytest node ID into the inner test body.
    :param other_loader_options: Additional keyword arguments forwarded verbatim to the loader decorator.
    """
    if collect_only and check_test_id:
        raise ValueError("check_test_id is not supported when collect_only=True")

    pytester = test_context.pytester
    loader = test_context.loader

    if path:
        test_context.path = path

    # Build the loader option list from explicit kwargs and any extras
    loader_options: list[str] = []
    if lazy_loading is False:
        loader_options.append(f"lazy_loading={lazy_loading}")
    func_defs = {
        DataLoaderFunctionType.ONLOAD_FUNC: onload_func_def,
        DataLoaderFunctionType.PARAMETRIZER_FUNC: parametrizer_func_def,
        DataLoaderFunctionType.FILTER_FUNC: filter_func_def,
        DataLoaderFunctionType.PROCESS_FUNC: process_func_def,
        DataLoaderFunctionType.MARKER_FUNC: marker_func_def,
        DataLoaderFunctionType.ID_FUNC: id_func_def,
        DataLoaderFunctionType.FILE_READER_FUNC: file_reader_func_def,
        DataLoaderFunctionType.READ_OPTION_FUNC: read_option_func_def,
    }
    for func_type, func_def in func_defs.items():
        if func_def is not None:
            loader_options.append(f"{func_type}={func_def}")
    if id_ is not None:
        loader_options.append(f"id={id_!r}")
    if other_loader_options:
        loader_options.extend(f"{k}={v!r}" for k, v in other_loader_options.items())
    loader_options_str = (", " + ", ".join(loader_options)) if loader_options else ""

    # Build path and fixture-name representations for the inner test
    is_abs_path = Path(test_context.path).is_absolute()

    # Make sure to apply repr() on the string value to handle window's path correctly
    if isinstance(test_context.path, Path):
        path_str = f"Path({str(test_context.path)!r})"
    else:
        path_str = f"{test_context.path!r}"

    if is_valid_fixture_names(fixture_names):
        if isinstance(fixture_names, str):
            fixture_names_str = fixture_names
        else:
            fixture_names_str = ",".join(fixture_names)
    else:
        # this doesn't matter as the test is expected to fail before running
        fixture_names_str = "_"

    fixtures = fixture_names_str.split(",")
    data_type = _infer_data_type(test_context.test_file_ext, loader)
    iterator_import = "from collections.abc import Iterator" if data_type == "Iterator" else ""

    test_code = f"""
    import os
    import json
    from pathlib import Path
    {iterator_import}

    import pytest
    from pytest_data_loader import {loader.__name__}
    from pytest_data_loader.utils import validate_loader_func_args_and_normalize

    data_dir = Path({str(test_context.data_dir)!r})

    @{loader.__name__}({fixture_names!r}, {path_str}{loader_options_str})
    def test(request, {fixture_names_str}):
        '''Checks the most basic functionality of pytest-data-loader plugin'''
        data_loader_root_dir = {repr(str(data_loader_root_dir)) if data_loader_root_dir else None}

        print()
        print(f"- data_loader_root_dir rootdir: {{data_loader_root_dir}}")
        print(f"- pytest rootdir: {{request.config.rootpath}}")
        print(f"- __file__: {{__file__}}")

        len_fixtures = len({fixtures})
        assert len_fixtures in (1, 2)

        if data_loader_root_dir:
            # Make sure the specified root dir is located outside of pytest rootdir
            assert request.config.rootpath.is_relative_to(data_loader_root_dir)

        if len({fixtures!r}) == 1:
            file_path = None
            data = {fixtures[0]}
            print(f"- data: {{repr(data)}}")
            assert isinstance(data, {data_type})
        else:
            file_path, data = {fixture_names_str}
            print(f"- file_path: {{repr(file_path)}}")
            print(f"- data: {{repr(data)}}")
            assert isinstance(file_path, Path)
            assert isinstance(data, {data_type})
            if data_loader_root_dir:
                assert file_path.is_relative_to(data_loader_root_dir)
                assert not file_path.is_relative_to(request.config.rootpath)
    """

    if check_test_id:
        assert len(fixtures) == 2, "This test requires to give 2 fixture names"
        test_code += _render_test_id_assertions_block(loader, fixtures, id_, id_func_def, is_abs_path, lazy_loading)

    pytester.makepyfile(test_code)
    cmd_options = ["--collect-only", "-q"] if collect_only else ["-vs"]
    return pytester.runpytest(*cmd_options)


def _render_test_id_assertions_block(
    loader: DataLoader,
    fixtures: list[str],
    id_: str | None,
    id_func_def: str | None,
    is_abs_path: bool,
    lazy_loading: bool | None,
) -> str:
    """Build the test-ID assertion block appended to the inner test body when ``check_test_id=True``.

    :param loader: The loader decorator under test.
    :param fixtures: List of fixture name strings (must have length 2).
    :param id_: Explicit id string for the ``@load`` decorator, or None.
    :param id_func_def: Python expression string for the ``id_func`` argument, or None.
    :param is_abs_path: Whether the path argument is absolute.
    :param lazy_loading: The lazy_loading option value used for the inner test.
    """
    return f"""
        has_id = {bool(id_)}
        has_id_func = {bool(id_func_def)}
        is_lazy_loading = {bool(lazy_loading)}
        is_abs_path = {bool(is_abs_path)}
        node_id = request.node.nodeid.encode("utf-8").decode("unicode_escape")  # normalized for windows
        if {loader.__name__}.__name__ == 'load':
            if has_id:
                assert node_id.endswith("[{id_}]")
            else:
                if is_abs_path:
                    assert node_id.endswith(f"[{{file_path}}]")
                else:
                    assert node_id.endswith(f"[{{file_path.relative_to(data_dir)}}]")
        elif {loader.__name__}.__name__ == 'parametrize':
            if has_id_func:
                id_func = eval({id_func_def!r})
                expected_id = validate_loader_func_args_and_normalize(id_func)(file_path, data)
                assert node_id.endswith(f"[{{expected_id}}]")
            else:
                if is_lazy_loading:
                    idx = request.node.callspec.indices['{fixtures[-1]}']
                    if is_abs_path:
                        assert node_id.endswith(f"[{{file_path}}:part{{idx+1}}]")
                    else:
                        assert node_id.endswith(f"[{{file_path.relative_to(data_dir)}}:part{{idx+1}}]")
                else:
                    assert node_id.endswith(f"[{{data!r}}]")
        else:
            if has_id_func:
                id_func = eval({id_func_def!r})
                expected_id = validate_loader_func_args_and_normalize(id_func, with_file_path_only=True)(
                    file_path, None
                )
                assert node_id.endswith(f"[{{expected_id}}]")
            elif is_abs_path:
                assert node_id.endswith(f"[{{file_path}}]")
            else:
                assert node_id.endswith(f"[{{file_path.relative_to(data_dir)}}]")

    """


def _infer_data_type(file_ext: str, loader: DataLoader) -> str:
    """Return the Python type name expected for data loaded from a file with the given extension.

    :param file_ext: File extension including the leading dot (e.g. ``".txt"``).
    :param loader: The loader decorator used for the inner test.
    """
    if file_ext == ".txt":
        return "str"
    if file_ext == ".json":
        return "tuple" if loader is parametrize else "dict"
    if file_ext == ".jsonl":
        return "dict" if loader is parametrize else "Iterator"
    if file_ext == ".png":
        return "bytes"
    raise NotImplementedError(f"Unsupported file type: {file_ext}")
