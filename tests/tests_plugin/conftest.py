import json
import os
import re
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from _pytest.fixtures import SubRequest
from pytest import MonkeyPatch, Pytester

from pytest_data_loader import load, parametrize, parametrize_dir
from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.types import DataLoader
from pytest_data_loader.utils import has_env_vars
from tests.tests_plugin.helper import LoaderRootDir, TestContext, create_test_file_in_loader_dir

pytest_plugins = "pytester"

if sys.platform == "win32":
    NEW_LINE = "\r\n"
else:
    NEW_LINE = "\n"
TRAILING_WHITESPACE = "  \t  "


@pytest.fixture(params=[load, parametrize, parametrize_dir])
def loader(request: SubRequest) -> DataLoader:
    """Parametrized loaders to test with

    To test a single loader, add @pytest.mark.parametrize("loader", [<the loader>]) to the test to override this fixture
    """
    return request.param


@pytest.fixture
def loader_dir_name(request: SubRequest) -> str:
    """Loader dir name. Supports indirect parametrization to override the default value"""
    if getattr(request, "param", None):
        return request.param
    return DEFAULT_LOADER_DIR_NAME


@pytest.fixture
def loader_root_dir(request: SubRequest, pytester: Pytester, monkeypatch: MonkeyPatch) -> Generator[LoaderRootDir]:
    """Loader root directory path. Supports indirect parametrization to override the default value"""
    orig_path = pytester.path
    loader_root = LoaderRootDir()
    if requested := getattr(request, "param", None):
        loader_root.requested_path = requested
        root_dir = request.param
        if has_env_vars(root_dir):
            # We use the original pytester dir as the expected env var value.
            # Then we manipulate the pytester dir so that the original dir gets placed outside the pytester dir
            if sys.platform == "win32":
                pattern_env_var = r"%(?P<var_name>[^}]+)%"
            else:
                pattern_env_var = r"\${?(?P<var_name>[^}]+)}?"
            matched = re.match(rf"{pattern_env_var}.*", root_dir)
            assert matched
            env_var = matched.group("var_name")

            # Set the root dir to the env var so that pytest can resolve it from the INI file
            monkeypatch.setenv(env_var, str(orig_path))

            # replace the env var with the original pytester dir
            root_dir = Path(re.sub(pattern_env_var, lambda m: str(orig_path), root_dir))
            assert root_dir.is_relative_to(orig_path)

            # Create the directory and change the pytester dir to it
            root_dir.mkdir(parents=True, exist_ok=True)
            pytester._path = root_dir
            pytester.chdir()

        # Create a new pytester dir under the current dir and change dir to it
        # At this point the new pytester dir will look like this:
        # <resolved loader root dir>/NEW_PYTESTER_DIR
        new_pytester_dir = "NEW_PYTESTER_DIR"
        pytester.mkdir(new_pytester_dir)
        pytester._path = pytester.path / new_pytester_dir
        pytester.chdir()

        # Resolve the loader root dir from the current pytester dir
        loader_root.resolved_path = Path(os.path.expandvars(root_dir)).resolve()

    yield loader_root
    if pytester.path != orig_path:
        pytester._path = orig_path
        pytester.chdir()


@pytest.fixture
def strip_trailing_whitespace(request: SubRequest) -> bool:
    """strip_trailing_whitespace option value. Supports indirect parametrization to override the default value"""
    if getattr(request, "param", None):
        return bool(request.param)
    return True


@pytest.fixture
def file_extension(request: SubRequest) -> str:
    """File extension to test. Supports indirect parametrization to override the default file type"""
    default_ext = ".txt"
    return getattr(request, "param", default_ext)


@pytest.fixture
def file_content(request: SubRequest, file_extension: str) -> str | bytes:
    """File content for the file extension requested for the current test"""
    ext_content_map: dict[str, str | bytes] = {
        ".txt": f"line1{NEW_LINE}line2{NEW_LINE}line3{TRAILING_WHITESPACE}{NEW_LINE}",
        ".json": json.dumps({"key1": "val1", "key2": "val2", "key3": "val3"}) + NEW_LINE,
        ".png": b"",  # will be filled when requested
    }
    if file_extension not in ext_content_map:
        raise NotImplementedError(f"Not supported for {file_extension} file")
    if file_extension == ".png":
        ext_content_map[file_extension] = request.getfixturevalue(png_file_content.__name__)
    return ext_content_map[file_extension]


@pytest.fixture(scope="session")
def png_file_content() -> bytes:
    """Some .png data"""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x01\x00\x00\x00\x007n\xf9$\x00\x00\x00\nIDATx"
        b"\x01c`\x00\x00\x00\x02\x00\x01su\x01\x18\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture
def test_context(
    pytester: Pytester,
    loader: DataLoader,
    loader_dir_name: str,
    file_extension: str,
    file_content: str | bytes,
    strip_trailing_whitespace: bool,
    loader_root_dir: LoaderRootDir,
) -> TestContext:
    """Test context fixture that sets up minimum data for various conditions passed via the dependent fixtures"""
    test_data_dir = pytester.mkdir(loader_dir_name)
    if loader.requires_file_path:
        relative_path = create_test_file_in_loader_dir(
            pytester,
            loader_dir_name,
            f"file{file_extension}",
            loader_root_dir=loader_root_dir.resolved_path,
            data=file_content,
        )
        if loader.requires_parametrization:
            if file_extension == ".json":
                num_expected_tests = len(json.loads(file_content).items())
            elif file_extension == ".txt":
                assert isinstance(file_content, str)
                if strip_trailing_whitespace:
                    num_expected_tests = len(file_content.rstrip().splitlines())
                else:
                    num_expected_tests = len(file_content.rstrip("\r\n").splitlines())
            elif file_extension == ".png":
                num_expected_tests = 1
            else:
                raise NotImplementedError(f"Not supported for {file_extension} file")
        else:
            num_expected_tests = 1
    else:
        relative_path = Path("dir")
        num_expected_tests = 2
        [
            create_test_file_in_loader_dir(
                pytester,
                loader_dir_name,
                relative_path / f"file{i}{file_extension}",
                loader_root_dir=loader_root_dir.resolved_path,
                data=file_content,
            )
            for i in range(num_expected_tests)
        ]

    return TestContext(
        pytester=pytester,
        loader=loader,
        loader_dir=test_data_dir,
        relative_path=relative_path,
        test_file_ext=file_extension,
        test_file_content=file_content,
        num_expected_tests=num_expected_tests,
    )
