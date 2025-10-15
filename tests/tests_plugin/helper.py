import os
from dataclasses import dataclass
from pathlib import Path

from _pytest.pytester import Pytester
from pytest import RunResult

from pytest_data_loader import load, parametrize
from pytest_data_loader.types import DataLoader
from pytest_data_loader.utils import is_valid_fixture_name


@dataclass(kw_only=True)
class TestContext:
    __test__ = False

    pytester: Pytester
    loader: DataLoader
    loader_dir: Path | str
    relative_path: Path | str
    test_file_ext: str
    test_file_content: str | bytes
    num_expected_tests: int


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


def create_test_file_in_loader_dir(
    pytester: Pytester,
    loader_dir: Path | str,
    relative_file_or_dir_path: Path | str,
    loader_root_dir: Path | None = None,
    is_dir: bool = False,
    file_name: str | None = None,
    data: str | bytes = "content",
) -> Path:
    relative_file_path: Path | str
    if is_dir:
        if not file_name:
            raise ValueError("file_name is required if is_dir=True")
        relative_file_path = Path(relative_file_or_dir_path) / file_name
    else:
        relative_file_path = relative_file_or_dir_path

    if loader_root_dir:
        loader_dir = loader_root_dir / loader_dir
    else:
        loader_dir = Path(loader_dir)

    file_path = loader_dir / relative_file_path
    name, ext = os.path.splitext(file_path)
    if ext == ".png":
        if not file_path.parent.exists():
            pytester.mkdir(file_path.parent)
        file_path.write_bytes(data)  # type: ignore
    else:
        pytester.makefile(ext, **{name: data})
    return file_path.relative_to(loader_dir)


def run_pytest_with_context(
    test_context: TestContext,
    fixture_names: str | tuple[str, ...] = ("arg1", "arg2"),
    data_loader_root_dir: Path | None = None,
    relative_data_path: Path | str | None = None,
    lazy_loading: bool | None = True,
    onload_func_def: str | None = None,
    parametrizer_func_def: str | None = None,
    filter_func_def: str | None = None,
    process_func_def: str | None = None,
    id_: str | None = None,
    id_func_def: str | None = None,
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
    if relative_data_path:
        test_context.relative_path = relative_data_path
    if lazy_loading is False:
        loader_options.append(f"lazy_loading={lazy_loading}")
    if onload_func_def:
        loader_options.append(f"onload_func={onload_func_def}")
    if parametrizer_func_def:
        loader_options.append(f"parametrizer_func={parametrizer_func_def}")
    if filter_func_def:
        loader_options.append(f"filter_func={filter_func_def}")
    if process_func_def:
        loader_options.append(f"process_func={process_func_def}")
    if id_:
        assert loader == load
        loader_options.append(f"id={id_!r}")
    if id_func_def:
        assert loader == parametrize
        loader_options.append(f"id_func={id_func_def}")
    loader_options_str = ", " + ", ".join(loader_options) if loader_options else ""

    # Make sure to apply repr() on the string value to handle window's path correctly
    if isinstance(test_context.relative_path, Path):
        rel_path_str = f"Path({str(test_context.relative_path)!r})"
    else:
        rel_path_str = f"{test_context.relative_path!r}"

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
    from pathlib import Path
    from pytest_data_loader import {loader.__name__}
    from pytest_data_loader.utils import bind_and_call_loader_func

    @{loader.__name__}({fixture_names!r}, {rel_path_str}{loader_options_str})
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
                expected_id = bind_and_call_loader_func(id_func, file_path, data)
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
