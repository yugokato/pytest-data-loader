import inspect
from collections.abc import Callable, Collection, Iterable
from pathlib import Path
from typing import Any, TypeVar, cast

from pytest import Mark, MarkDecorator

from pytest_data_loader.compat import Unpack
from pytest_data_loader.constants import PYTEST_DATA_LOADER_ATTR
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    DataLoaderType,
    FileReadOptions,
    HashableDict,
    TestFunc,
)

T = TypeVar("T", bound=Callable[..., Any])

__all__ = ["load", "parametrize", "parametrize_dir"]


def loader(loader_type: DataLoaderType, /, *, parametrize: bool = False) -> Callable[[T], T]:
    """Decorator to register a decorated function as a data loader

    :param loader_type: A type of the loader. file or directory
    :param parametrize: Whether the loader needs to perform parametrization or not
    """

    def wrapper(loader_func: T) -> T:
        loader_func.is_file_loader = DataLoaderType(loader_type) == DataLoaderType.FILE  # type: ignore[attr-defined]
        loader_func.requires_parametrization = parametrize is True  # type: ignore[attr-defined]
        loader_func.should_split_data = bool(loader_func.is_file_loader and loader_func.requires_parametrization)  # type: ignore[attr-defined]
        return loader_func

    return wrapper


@loader(DataLoaderType.FILE)
def load(
    fixture_names: str | tuple[str, str],
    path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    file_reader: Callable[..., Iterable[Any] | object] | None = None,
    onload_func: Callable[..., Any] | None = None,
    id: str | None = None,
    **read_options: Unpack[FileReadOptions],
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that loads the file content and passes it to the test function.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param path: Path to the file to load. It can be either an absolute path or a path relative to one of the base data
                 directories. When a relative path is provided, the loader searches for the nearest data directory
                 containing a matching file and loads the data from there.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param file_reader: A file reader the plugin should use to read the file data.
                        (e.g. csv.reader, csv.DictReader, yaml.safe_load, etc.)
                        It must take a file-like object as the first argument. If the file_reader needs to take
                        options, use lambda function instead.
                        e.g. file_reader=lambda f: csv.reader(f, delimiter=';')
                        NOTE: The test function will receive the reader object as is
    :param onload_func: A function to transform or preprocess loaded data before passing it to the test function.
                        NOTE: .json files will always be automatically parsed during the plugin-managed onload process
    :param id: Explicitly specify the parameter ID for the loaded data. Defaults to the file name.
    :param read_options: File read options the plugin passes to `open()` when reading the file. Supports only mode,
                         encoding, errors, and newline options.

    NOTE:
        - onload_func loader function must take either one (data) or two (file path, data) arguments. When file_reader
          is provided, the data is the reader object itself

    Examples:
    >>> @load("data", "data.txt")
    >>> def test_example(data: str):
    >>>     assert data == "foo\\nbar"
    >>>
    >>> @load(("file_path", "data"), "data.json")
    >>> def test_example2(file_path: Path, data: dict[str, Any]):
    >>>     assert file_path.name == "data.json"
    >>>     assert data == {"key": "value"}
    """
    return _setup_data_loader(
        cast(DataLoader, load),
        fixture_names,
        path,
        lazy_loading=lazy_loading,
        file_reader=file_reader,
        onload_func=onload_func,
        id_func=(lambda _: id) if id is not None else None,
        **read_options,
    )


@loader(DataLoaderType.FILE, parametrize=True)
def parametrize(
    fixture_names: str | tuple[str, str],
    path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    file_reader: Callable[..., Iterable[Any] | object] | None = None,
    onload_func: Callable[..., Any] | None = None,
    parametrizer_func: Callable[..., Iterable[Any]] | None = None,
    filter_func: Callable[..., bool] | None = None,
    process_func: Callable[..., Any] | None = None,
    marker_func: Callable[..., MarkDecorator | Collection[MarkDecorator | Mark] | None] | None = None,
    id_func: Callable[..., Any] | None = None,
    **read_options: Unpack[FileReadOptions],
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that dynamically parametrizes the decorated test function by splitting the loaded file content
    into logical parts.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded part data will be passed to that fixture. If two names are
                          provided either as a tuple or as a comma-separated string, the first fixture will receive the
                          file path, and the second will receive the loaded part data.
    :param path: Path to the file to load. It can be either an absolute path or a path relative to one of the base data
                 directories. When a relative path is provided, the loader searches for the nearest data directory
                 containing a matching file and loads the data from there.
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
    :param file_reader: A file reader the plugin should use to read the file data.
                        (e.g. csv.reader, csv.DictReader, yaml.safe_load, etc.)
                        It must take a file-like object as the first argument. If the file_reader needs to take
                        options, use lambda function.
                        e.g. file_reader=lambda f: csv.reader(f, delimiter=';')
    :param onload_func: A function to transform or preprocess loaded data before splitting into parts.
                        NOTE: .json files will always be automatically parsed during the plugin-managed onload process
    :param parametrizer_func: A function to determine how the loaded data should be split. If not provided, the plugin
                              will automatically apply the following logic:
                              - .json file:
                                    - array: each item in the list
                                    - object: each key-value pair as a tuple
                                    - scalar: the whole value as a single parameter
                              - Any other files with text data (.txt, .csv, .log, etc.): each line
                              - Binary files: Not supported without a custom logic. An error will be raised.
    :param filter_func: A function to filter the split data parts. Only matching parts are included as the test
                        parameters.
    :param process_func: A function to adjust the shape of each split data before passing it to the test function.
    :param marker_func: A function to apply Pytest markers to mathing part data
    :param id_func: A function to generate a parameter ID for each part data. Defaults to "<file_name>:part<number>"
                    when lazy loading, otherwise the part data itself is used.
    :param read_options: File read options the plugin passes to `open()` when reading the file. Supports only mode,
                         encoding, errors, and newline options.

    NOTE:
        - Each loader function must take either one (data) or two (file path, data) arguments. When file_reader
          is provided, the data is the reader object itself

    Examples:
    >>> @parametrize("data", "data.txt")
    >>> def test_example(data: list[str]):
    >>>     assert data in ["foo", "bar"]
    >>>
    >>> @parametrize(("file_path", "data"), "data.json")
    >>> def test_example2(file_path: Path, data: list[tuple[str, str]]):
    >>>     assert file_path.name == "data.json"
    >>>     assert data in [("key1": "value1"), ("key2": "value2")]
    >>>
    """
    return _setup_data_loader(
        cast(DataLoader, parametrize),
        fixture_names,
        path,
        lazy_loading=lazy_loading,
        file_reader=file_reader,
        onload_func=onload_func,
        parametrizer_func=parametrizer_func,
        filter_func=filter_func,
        process_func=process_func,
        marker_func=marker_func,
        id_func=id_func,
        **read_options,
    )


@loader(DataLoaderType.DIRECTORY, parametrize=True)
def parametrize_dir(
    fixture_names: str | tuple[str, str],
    path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    recursive: bool = False,
    file_reader_func: Callable[[Path], Callable[..., Iterable[Any] | object]] | None = None,
    filter_func: Callable[[Path], bool] | None = None,
    process_func: Callable[..., Any] | None = None,
    marker_func: Callable[[Path], MarkDecorator | Collection[MarkDecorator | Mark] | None] | None = None,
    read_option_func: Callable[[Path], dict[str, Any]] | None = None,
) -> Callable[[TestFunc], TestFunc]:
    """A file loader that dynamically parametrizes the decorated test function with the content of files stored in the
    specified directory.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param path: Path to the directory to load files from. It can be either an absolute path or a path relative to one
                 of the data directories. When a relative path is provided, the loader searches for the nearest data
                 directory containing a matching directory and loads files from there.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param recursive: Recursively load files from all subdirectories of the given directory. Defaults to False
    :param file_reader_func: A function to specify file readers to matching file paths.
    :param filter_func: A function to filter file paths. Only the contents of matching file paths are included as the
                        test parameters.
    :param process_func: A function to adjust the shape of each loaded file's data before passing it to the test
                         function.
                         NOTE: .json files will always be automatically parsed during the plugin-managed onload process
    :param marker_func: A function to apply Pytest markers to mathing file paths
    :param read_option_func: A function to specify file read options the plugin passes to `open()` to matching file
                             paths. Supports only mode, encoding, errors, and newline options. It must return these
                             options as a dictionary.

    NOTE:
        - file_reader_func, filter_func, marker_func, and read_option_func must take only one argument (file path)
        - process_func loader function must take either one (data) or two (file path, data) arguments
        - The plugin automatically asigns each file name to the parameter ID

    Examples:
    >>> @parametrize_dir("data", "data_dir")
    >>> def test_example(data: str):
    >>>     assert data in ["foo", "bar", "baz"]
    >>>
    >>> @parametrize_dir(("file_path", "data"), "data_dir")
    >>> def test_example2(file_path: Path, data: str):
    >>>     assert file_path.name in ["data1.txt", "data2.txt", "data3.txt"]
    >>>     assert data in ["foo", "bar", "baz"]
    """
    return _setup_data_loader(
        cast(DataLoader, parametrize_dir),
        fixture_names,
        path,
        lazy_loading=lazy_loading,
        recursive=recursive,
        file_reader_func=file_reader_func,
        filter_func=filter_func,
        process_func=process_func,
        marker_func=marker_func,
        read_option_func=read_option_func,
    )


def _setup_data_loader(
    loader: DataLoader,
    fixture_names: str | tuple[str, str],
    path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    recursive: bool = False,
    file_reader: Callable[..., Iterable[Any] | object] | None = None,
    file_reader_func: Callable[..., Callable[..., Iterable[Any] | object]] | None = None,
    onload_func: Callable[..., Any] | None = None,
    parametrizer_func: Callable[..., Iterable[Any]] | None = None,
    filter_func: Callable[..., bool] | None = None,
    process_func: Callable[..., Any] | None = None,
    id_func: Callable[..., Any] | None = None,
    marker_func: Callable[..., MarkDecorator | Collection[MarkDecorator | Mark] | None] | None = None,
    read_option_func: Callable[[Path], dict[str, Any]] | None = None,
    **read_options: Unpack[FileReadOptions],
) -> Callable[[TestFunc], TestFunc]:
    """Set up a test function and inject loder attributes that are used by pytest_generate_tests hook"""

    if not loader.requires_parametrization and any([parametrizer_func, filter_func, process_func]):
        raise ValueError(
            f"Invalid usage: parametrizer_func, filter_func, and process_func are not supported for "
            f"{loader.__name__} loader"
        )
    if recursive and not loader == parametrize_dir:
        raise ValueError(f"recursive option is not available for {loader.__name__} loader")

    def wrapper(test_func: TestFunc) -> TestFunc:
        """Add attributes to the test function"""
        setattr(
            test_func,
            PYTEST_DATA_LOADER_ATTR,
            DataLoaderLoadAttrs(
                loader=loader,
                search_from=Path(inspect.getabsfile(test_func)),
                # fixture_names and path will be validated and normalized in __post_init__()
                fixture_names=cast(tuple[str, ...], fixture_names),
                path=cast(Path, path),
                lazy_loading=lazy_loading,
                recursive=recursive,
                file_reader=file_reader,
                file_reader_func=file_reader_func,
                onload_func=onload_func,
                parametrizer_func=parametrizer_func,
                filter_func=filter_func,
                process_func=process_func,
                marker_func=marker_func,
                id_func=id_func,
                read_option_func=read_option_func,
                read_options=HashableDict(read_options),
            ),
        )
        return test_func

    return wrapper
