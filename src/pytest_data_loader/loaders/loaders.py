from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from pytest_data_loader.constants import PYTEST_DATA_LOADER_ATTR
from pytest_data_loader.types import DataLoader, DataLoaderLoadAttrs, DataLoaderPathType, LoadedDataType, TestFunc

from .impl import loader

__all__ = ["load", "parametrize", "parametrize_dir"]


@loader(DataLoaderPathType.FILE)
def load(
    fixture_names: str | tuple[str, str],
    relative_path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    force_binary: bool = False,
    onload_func: Callable[..., LoadedDataType] | None = None,
    id: str | None = None,
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that loads the file content and passes it to the test function.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param relative_path: File path relative to one of the base data loader directories. The loader searches for the
                          closest data loader directory containing a matching file and loads the data from there.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param force_binary: If True, the file will be read in binary mode. Default is auto-detected based on file content.
    :param onload_func: A function to transform or preprocess loaded data before passing it to the test function.
                        NOTE: .json files will always be automatically parsed during the plugin-managed onload process
    :param id: Explicitly specify the parameter ID for the loaded data. Defaults to the file name.

    NOTE:
        - onload_func loader function must take either one (data) or two (file path, data) arguments

    Examples:
    >>> @load("data", "data.txt")
    >>> def test_example(data: LoadedDataType):
    >>>     assert data == "foo\\nbar"
    >>>
    >>> @load(("file_path", "data"), "data.json")
    >>> def test_example2(file_path: Path, data: LoadedDataType):
    >>>     assert file_path.name == "data.json"
    >>>     assert data == {"key": "value"}
    """
    return _setup_data_loader(
        cast(DataLoader, load),
        fixture_names,
        relative_path,
        lazy_loading=lazy_loading,
        force_binary=force_binary,
        onload_func=onload_func,
        id_func=(lambda _: id) if id is not None else None,
    )


@loader(DataLoaderPathType.FILE, parametrize=True)
def parametrize(
    fixture_names: str | tuple[str, str],
    relative_path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    onload_func: Callable[..., LoadedDataType] | None = None,
    parametrizer_func: Callable[..., Iterable[LoadedDataType]] | None = None,
    filter_func: Callable[..., bool] | None = None,
    process_func: Callable[..., LoadedDataType] | None = None,
    id_func: Callable[..., Any] | None = None,
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that dynamically parametrizes the decorated test function by splitting the loaded file content
    into logical parts.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded part data will be passed to that fixture. If two names are
                          provided either as a tuple or as a comma-separated string, the first fixture will receive the
                          file path, and the second will receive the loaded part data.
    :param relative_path: File path relative to one of the base data loader directories. The loader searches for the
                          closest data loader directory containing a matching file and loads the data from there.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. Note that
                         unlike other loaders, the plugin still needs to inspect the file data during the collection
                         phase to determine the total number of parametrized tests. The inspection is done in one of
                         the following modes, depending on the file type and specified options:
                         1. Quick scan: Applies to certain file extensions only, and only when neither `onload_func`
                            nor `parametrizer_func` is provided. the plugin determines the number of parametrized
                            tests without loading the entire file contents in memory.
                         2. Full scan: The plugin loads the entire file once during the collection phase to determine
                                       the number of parametrized tests, but it does not keep the loaded data in memory.
                         In both modes, Pytest receives only small metadata (such as file paths and record indices) as
                         parameters. The actual data associated with each parameter is loaded lazily when needed
                         during the test setup phase.
                         If False, Pytest will receive the fully loaded data for each parameter during test collection
                         and retain it for the entire test session. This can lead to significant memory usage when
                         working with large files.
    :param onload_func: A function to transform or preprocess loaded data before splitting into parts.
                        NOTE: .json files will always be automatically parsed during the plugin-managed onload process
    :param parametrizer_func: A function to determine how the loaded data should be split. If not provided, the plugin
                              will automatically apply the following logic:
                              - .json file:
                                    - array: each item in the list
                                    - object: each key-value pair as a tuple
                                    - scalar: the whole value as a single parameter
                              - Any other files with text data (.txt, .csv, .log, etc.): each line
                              - Binary files: Not supported without a cusom logic. An error will be raised.
    :param filter_func: A function to filter the split data parts. Only matching parts are included as the test
                        parameters.
    :param process_func: A function to adjust the shape of each split data before passing it to the test function.
    :param id_func: A function to generate a parameter ID for each part data. Defaults to "<file_name>:part<number>"
                    when lazy loading, otherwise the part data itself is used.

    NOTE:
        - Each loader function must take either one (data) or two (file path, data) arguments

    Examples:
    >>> @parametrize("data", "data.txt")
    >>> def test_example(data: LoadedDataType):
    >>>     assert data in ["foo", "bar"]
    >>>
    >>> @parametrize(("file_path", "data"), "data.json")
    >>> def test_example2(file_path: Path, data: LoadedDataType):
    >>>     assert file_path.name == "data.json"
    >>>     assert data in [("key1": "value1"), ("key2": "value2")]
    >>>
    """
    return _setup_data_loader(
        cast(DataLoader, parametrize),
        fixture_names,
        relative_path,
        lazy_loading=lazy_loading,
        filter_func=filter_func,
        onload_func=onload_func,
        parametrizer_func=parametrizer_func,
        process_func=process_func,
        id_func=id_func,
    )


@loader(DataLoaderPathType.DIRECTORY, parametrize=True)
def parametrize_dir(
    fixture_names: str | tuple[str, str],
    relative_path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    force_binary: bool = False,
    filter_func: Callable[..., bool] | None = None,
    process_func: Callable[..., LoadedDataType] | None = None,
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that dynamically parametrizes the decorated test function with the content of files stored in the
    specified directory.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param relative_path: Directory path relative to one of the base data loader directories. The loader searches for
                          the closest data loader directory containing a matching directory and loads files from there.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param force_binary: If True, each file will be read in binary mode. Default is auto-detected based on file content.
    :param filter_func: A function to filter file paths. Only the contents of matching file paths are included as the
                        test parameters.
    :param process_func: A function to adjust the shape of each loaded file's data before passing it to the test
                         function.
                         NOTE: .json files will always be automatically parsed during the plugin-managed onload process

    NOTE:
        - filter_func must take only one argument (file path)
        - process_func loader function must take either one (data) or two (file path, data) arguments
        - The plugin automatically asigns each file name to the parameter ID

    Examples:
    >>> @parametrize_dir("data", "data_dir")
    >>> def test_example(data: LoadedDataType):
    >>>     assert data in ["foo", "bar", "baz"]
    >>>
    >>> @parametrize_dir(("file_path", "data"), "data_dir")
    >>> def test_example2(file_path: Path, data: LoadedDataType):
    >>>     assert file_path.name in ["data1.txt", "data2.txt", "data3.txt"]
    >>>     assert data in ["foo", "bar", "baz"]
    """
    return _setup_data_loader(
        cast(DataLoader, parametrize_dir),
        fixture_names,
        relative_path,
        force_binary=force_binary,
        filter_func=filter_func,
        process_func=process_func,
        lazy_loading=lazy_loading,
    )


def _setup_data_loader(
    loader: DataLoader,
    fixture_names: str | tuple[str, str],
    relative_path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    force_binary: bool = False,
    onload_func: Callable[..., LoadedDataType] | None = None,
    parametrizer_func: Callable[..., Iterable[LoadedDataType]] | None = None,
    filter_func: Callable[..., bool] | None = None,
    process_func: Callable[..., LoadedDataType] | None = None,
    id_func: Callable[..., Any] | None = None,
) -> Callable[[TestFunc], TestFunc]:
    """Set up a test function and inject loder attributes that are used by pytest_generate_tests hook"""

    if not loader.requires_parametrization and any([parametrizer_func, filter_func, process_func]):
        raise ValueError(
            f"Invalid usage: parametrizer_func, filter_func, and process_func are not supported for "
            f"{loader.__name__} loader"
        )

    def wrapper(test_func: TestFunc) -> TestFunc:
        """Add attributes to the test function"""
        setattr(
            test_func,
            PYTEST_DATA_LOADER_ATTR,
            DataLoaderLoadAttrs(
                loader=loader,
                # fixture_names and relative_path will be validated and normalized in __post_init__()
                fixture_names=cast(tuple[str, ...], fixture_names),
                relative_path=cast(Path, relative_path),
                lazy_loading=lazy_loading,
                force_binary=force_binary,
                onload_func=onload_func,
                parametrizer_func=parametrizer_func,
                filter_func=filter_func,
                process_func=process_func,
                id_func=id_func,
            ),
        )
        return test_func

    return wrapper
