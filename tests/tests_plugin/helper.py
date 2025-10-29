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
    __test__ = False

    pytester: Pytester
    loader: DataLoader
    loader_dir: Path | str
    path: Path | str
    test_file_ext: str
    test_file_content: str | bytes
    strip_trailing_whitespace: bool = True

    @property
    def num_expected_tests(self) -> int:
        if self.loader.is_file_loader:
            if self.loader.requires_parametrization:
                if self.test_file_ext == ".json":
                    num_expected_tests = len(json.loads(self.test_file_content).items())
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
            num_expected_tests = len(list(Path(self.loader_dir, self.path).resolve().iterdir()))
        return num_expected_tests


@dataclass
class LoaderRootDir:
    requested_path: str | None = None
    resolved_path: Path | None = None


def is_valid_fixture_names(args: str | tuple[str, ...]) -> bool:
    if isinstance(args, str):
        args = tuple(x.strip() for x in args.split(","))
    else:
        args = tuple(args)
    return 0 < len(args) < 3 and all(is_valid_fixture_name(x) for x in args)


def get_num_func_args(loader_func: Callable[..., Any]) -> int:
    sig = inspect.signature(loader_func)
    parameters = sig.parameters
    return len(parameters)


def create_test_data_in_loader_dir(
    pytester: Pytester,
    loader_dir: Path | str,
    relative_file_path: Path | str,
    loader_root_dir: Path | None = None,
    data: str | bytes = "content",
    return_abs_path: bool = False,
) -> Path:
    if loader_root_dir:
        loader_dir = loader_root_dir / loader_dir
    else:
        loader_dir = Path(loader_dir)

    abs_file_path = (loader_dir / relative_file_path).resolve()
    if not abs_file_path.parent.exists():
        abs_file_path.parent.mkdir(parents=True, exist_ok=True)
    name, ext = os.path.splitext(abs_file_path)
    if ext == ".png":
        abs_file_path.write_bytes(data)  # type: ignore
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
    loader_dir_name: str = DEFAULT_LOADER_DIR_NAME,
    loader_root_dir: LoaderRootDir = LoaderRootDir(),
    strip_trailing_whitespace: bool = True,
    path_type: type[str | Path] = str,
    is_abs_path: bool = False,
) -> TestContext:
    test_data_dir = pytester.mkdir(loader_dir_name)
    if parent_dirs:
        Path(test_data_dir, parent_dirs).mkdir(parents=True, exist_ok=True)
    if loader.is_file_loader:
        path = create_test_data_in_loader_dir(
            pytester,
            loader_dir_name,
            Path(parent_dirs, f"file{file_extension}"),
            loader_root_dir=loader_root_dir.resolved_path,
            data=file_content,
            return_abs_path=is_abs_path,
        )
    else:
        path = Path(parent_dirs, "dir")
        paths = {
            create_test_data_in_loader_dir(
                pytester,
                loader_dir_name,
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
        loader_dir=test_data_dir,
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
) -> RunResult:
    """Common test logic that runs pytest via pytester with various test context and checks the basic functionality
    of pytest-data-loader plugin
    """
    if collect_only and check_test_id:
        raise ValueError("check_test_id is not supported when collect_only=True")

    pytester = test_context.pytester
    loader = test_context.loader
    loader_options = []
    if path:
        test_context.path = path
    if lazy_loading is False:
        loader_options.append(f"lazy_loading={lazy_loading}")
    if onload_func_def:
        loader_options.append(f"{DataLoaderFunctionType.ONLOAD_FUNC}={onload_func_def}")
    if parametrizer_func_def:
        loader_options.append(f"{DataLoaderFunctionType.PARAMETRIZER_FUNC}={parametrizer_func_def}")
    if filter_func_def:
        loader_options.append(f"{DataLoaderFunctionType.FILTER_FUNC}={filter_func_def}")
    if process_func_def:
        loader_options.append(f"{DataLoaderFunctionType.PROCESS_FUNC}={process_func_def}")
    if marker_func_def:
        loader_options.append(f"{DataLoaderFunctionType.MARKER_FUNC}={marker_func_def}")
    if id_:
        loader_options.append(f"id={id_!r}")
    if id_func_def:
        loader_options.append(f"{DataLoaderFunctionType.ID_FUNC}={id_func_def}")
    if file_reader_func_def:
        loader_options.append(f"{DataLoaderFunctionType.FILE_READER_FUNC}={file_reader_func_def}")
    if read_option_func_def:
        loader_options.append(f"{DataLoaderFunctionType.READ_OPTION_FUNC}={read_option_func_def}")
    loader_options_str = ", " + ", ".join(loader_options) if loader_options else ""

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
    if test_context.test_file_ext == ".txt":
        data_type = "str"
    elif test_context.test_file_ext == ".json":
        if loader == parametrize:
            data_type = "tuple"
        else:
            data_type = "dict"
    elif test_context.test_file_ext == ".png":
        data_type = "bytes"
    else:
        raise NotImplementedError(f"Unsupported file type: {test_context.test_file_ext}")

    test_code = f"""
    import os
    import json
    from pathlib import Path

    import pytest
    from pytest_data_loader import {loader.__name__}
    from pytest_data_loader.utils import validate_loader_func_args_and_normalize

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
        test_code += f"""

        has_id = {bool(id_)}
        has_id_func = {bool(id_func_def)}
        is_lazy_loading = {bool(lazy_loading)}
        if {loader.__name__}.__name__ == 'load':
            if has_id:
                assert request.node.name.endswith("[{id_}]")
            else:
                assert request.node.name.endswith(f"[{{file_path.name}}]")
        elif {loader.__name__}.__name__ == 'parametrize':
            if has_id_func:
                id_func = eval({id_func_def!r})
                expected_id = validate_loader_func_args_and_normalize(id_func)(file_path, data)
                assert request.node.name.endswith(f"[{{expected_id}}]")
            else:
                if is_lazy_loading:
                    idx = request.node.callspec.indices['{fixtures[-1]}']
                    assert request.node.name.endswith(f"[{{file_path.name}}:part{{idx+1}}]")
                else:
                    assert request.node.name.endswith(f"[{{data!r}}]")
        else:
            assert request.node.name.endswith(f"[{{file_path.name}}]")

    """
    pytester.makepyfile(test_code)

    # print(f"\ntest code:\n{test_code}")
    if collect_only:
        cmd_options = ["--collect-only", "-q"]
    else:
        cmd_options = ["-vs"]
    return pytester.runpytest(*cmd_options)
