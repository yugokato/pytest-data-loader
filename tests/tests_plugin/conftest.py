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
from pytest_data_loader.paths import has_env_vars
from pytest_data_loader.types import DataLoader
from tests.tests_plugin.helper import LoaderRootDir, TestContext, create_test_context

pytest_plugins = "pytester"

if sys.platform == "win32":
    NEW_LINE = "\r\n"
    # Matches %VAR_NAME% style environment variable references on Windows
    _ENV_VAR_PATTERN = r"%(?P<var_name>[^%]+)%"
else:
    NEW_LINE = "\n"
    # Matches ${VAR_NAME} and $VAR_NAME style environment variable references on POSIX
    _ENV_VAR_PATTERN = r"\${?(?P<var_name>[^}]+)}?"
TRAILING_WHITESPACE = "  \t  "


@pytest.fixture(params=[load, parametrize, parametrize_dir])
def loader(request: SubRequest) -> DataLoader:
    """Parametrized loaders to test with

    To test a single loader, add @pytest.mark.parametrize("loader", [<the loader>]) to the test to override this fixture
    """
    return request.param


@pytest.fixture
def data_dir_name(request: SubRequest) -> str:
    """Data dir name. Supports indirect parametrization to override the default value"""
    return getattr(request, "param", DEFAULT_LOADER_DIR_NAME)


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
            matched = re.match(rf"{_ENV_VAR_PATTERN}.*", root_dir)
            assert matched
            env_var = matched.group("var_name")

            # Set the root dir to the env var so that pytest can resolve it from the INI file
            monkeypatch.setenv(env_var, str(orig_path))

            # replace the env var with the original pytester dir
            root_dir = Path(re.sub(_ENV_VAR_PATTERN, lambda m: str(orig_path), root_dir))
            assert root_dir.is_relative_to(orig_path)

            # pytester._path is a private attribute. We mutate it here so that all subsequent
            # pytester.mkdir / makepyfile calls land inside root_dir (the resolved loader-root-dir)
            # rather than the default pytester temp directory. This is necessary because the plugin
            # validates that the pytest rootdir is a sub-path of data_loader_root_dir, which only
            # holds when the pytester working directory is physically nested inside it.
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
    """File extension under test. Supports indirect parametrization to override the default file type."""
    return getattr(request, "param", ".txt")


@pytest.fixture
def file_content(request: SubRequest, file_extension: str) -> str | bytes:
    """File content for the file extension requested for the current test"""
    jsonl_lines = [
        json.dumps({"key": "val1"}),
        json.dumps({"key": "val2"}),
        json.dumps({"key": "val3"}),
    ]
    ext_content_map: dict[str, str | bytes] = {
        ".txt": f"line1{NEW_LINE}line2{NEW_LINE}line3{TRAILING_WHITESPACE}{NEW_LINE}",
        ".json": json.dumps({"key1": "val1", "key2": "val2", "key3": "val3"}) + NEW_LINE,
        ".jsonl": NEW_LINE.join(jsonl_lines) + NEW_LINE,
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
def is_abs_path(request: SubRequest) -> bool:
    """Specify abs path or not. Supports indirect parametrization to override the default value"""
    if getattr(request, "param", None):
        return bool(request.param)
    return False


@pytest.fixture
def test_context(
    pytester: Pytester,
    loader: DataLoader,
    data_dir_name: str,
    file_extension: str,
    file_content: str | bytes,
    loader_root_dir: LoaderRootDir,
    strip_trailing_whitespace: bool,
    is_abs_path: bool,
) -> TestContext:
    """Test context fixture that sets up minimum data for various conditions passed via the dependent fixtures"""
    return create_test_context(
        pytester,
        loader,
        file_extension=file_extension,
        file_content=file_content,
        data_dir_name=data_dir_name,
        loader_root_dir=loader_root_dir,
        strip_trailing_whitespace=strip_trailing_whitespace,
        is_abs_path=is_abs_path,
    )
