import inspect
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from pytest_data_loader.constants import PYTEST_DATA_LOADER_ATTRS
from pytest_data_loader.loaders.impl import loader
from pytest_data_loader.types import (
    DataLoader,
    DataLoaderLoadAttrs,
    Func,
    PytestMarkType,
    ReadOptions,
)
from pytest_data_loader.validators import validate_loader_options

__all__ = ["load", "parametrize", "parametrize_dir"]


@loader
def load(
    fixture_names: str | tuple[str, str],
    path: Path | str,
    /,
    *,
    lazy_loading: bool = True,
    reader: Callable[..., Iterable[Any] | object] | None = None,
    onload: Callable[..., Any] | None = None,
    read_options: ReadOptions | None = None,
    marks: PytestMarkType | None = None,
    id: str | None = None,
) -> Callable[[Func], Func]:
    """A file loader that loads the file content and passes it to the test function.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param path: Path to the file to load. It can be either an absolute path or a path relative to one of the base data
                 directories. When a relative path is provided, the loader searches for the nearest data directory
                 containing a matching file and loads the data from there.
                 Environment variables are supported using the ``${VAR}`` or ``$VAR`` (or ``%VAR%`` for Windows) syntax.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param reader: A file reader the plugin should use to read the file data.
                   (e.g. csv.reader, csv.DictReader, yaml.safe_load, etc.)
                   It must take a file-like object as the first argument. If the reader needs to take options, use a
                   lambda instead. e.g. reader=lambda f: csv.reader(f, delimiter=';')
    :param read_options: File read options (as a dict) the plugin passes to `open()` when reading the file.
                         Supports only the mode, encoding, errors, and newline keys.
    :param onload: A function to transform or process loaded data before passing it to the test function.
    :param marks: Pytest mark(s) to apply to the loaded data. Accepts a single mark or a collection of marks
    :param id: Explicitly specify the parameter ID for the loaded data. Defaults to the relative or absolute file path

    NOTE:
        - onload must take either one (data) or two (file path, data) arguments. When reader is provided,
          its return value becomes the data passed to onload()

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
        reader=reader,
        read_options=read_options,
        onload=onload,
        ids=[id] if id is not None else None,
        marks=marks,
    )


@loader
def parametrize(
    fixture_names: str | tuple[str, str],
    path: Path | str | Sequence[Path | str],
    /,
    *,
    lazy_loading: bool = True,
    reader: Callable[..., Iterable[Any] | object] | None = None,
    read_options: ReadOptions | None = None,
    onload: Callable[..., Any] | None = None,
    parametrizer: Callable[..., Iterable[Any]] | None = None,
    filter: Callable[..., bool] | None = None,
    processor: Callable[..., Any] | None = None,
    marks: PytestMarkType | Callable[..., PytestMarkType | None] | None = None,
    ids: Iterable[Any] | Callable[..., Any] | None = None,
) -> Callable[[Func], Func]:
    """A file loader that dynamically parametrizes the decorated test function by splitting the loaded file content
    into logical parts.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded part data will be passed to that fixture. If two names are
                          provided either as a tuple or as a comma-separated string, the first fixture will receive the
                          file path, and the second will receive the loaded part data.
    :param path: Path to the file (or a list of file paths, a glob pattern, or a list that mixes both) to load. It
                 can be either an absolute path or a path relative to one of the base data directories. When a relative
                 path is provided, the loader searches for the nearest data directory containing a matching file and
                 loads the data from there.
                 When the provided path represents multiple files, the plugin loads and splits each file independently,
                 then concatenates all parametrized data into a single parameter list.
                 Environment variables are supported using the ``${VAR}`` or ``$VAR`` (or ``%VAR%`` for Windows) syntax.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. Note that
                         unlike other loaders, the plugin still needs to inspect the file data during the collection
                         phase to determine the total number of parametrized tests. The inspection is done in one of
                         the following modes, depending on the file type and specified options:
                         1. Quick scan: Applies to certain file extensions only, and only when neither `onload` nor
                            `parametrizer` is provided. The plugin determines the number of parametrized tests without
                            loading the entire file contents in memory.
                         2. Full scan: The plugin loads the entire file once during the collection phase to determine
                                       the number of parametrized tests, but it does not keep the loaded data in memory.
                         In both modes, Pytest receives only small metadata (such as file paths and record indices) as
                         parameters. The actual data associated with each parameter is loaded lazily when needed
                         during the test setup phase.
                         If False, Pytest will receive the fully loaded data for each parameter during test collection
                         and retain it for the entire test session. This can lead to significant memory usage when
                         working with large files.
    :param reader: A file reader the plugin should use to read the file data.
                   (e.g. csv.reader, csv.DictReader, yaml.safe_load, etc.)
                   It must take a file-like object as the first argument. If the reader needs to take options, use a
                   lambda instead. e.g. reader=lambda f: csv.reader(f, delimiter=';')
    :param read_options: File read options (as a dict) the plugin passes to `open()` when reading the file.
                         Supports only the mode, encoding, errors, and newline keys.
    :param onload: A function to transform or preprocess loaded data before splitting into parts.
    :param parametrizer: A function to determine how the loaded data should be split. If not provided, the plugin
                         will automatically apply the following logic:
                         - .json file:
                               - array: each item in the list
                               - object: each key-value pair as a tuple
                               - scalar: the whole value as a single parameter
                         - Any other files with text data (.txt, .csv, .log, etc.): each line
                         - Binary files: Not supported without a custom logic. An error will be raised.
    :param filter: A function to filter the split data parts. Only matching parts are included as the test parameters.
    :param processor: A function to adjust the shape of each part data before passing it to the test function.
    :param marks: Pytest mark(s) for the loaded parts. Accepts a single mark or a collection of marks applied uniformly
                  to all parts, or a function that returns mark(s) per part data.
    :param ids: Parameter IDs for the loaded parts. Accepts an iterable of ID values or a function that returns an ID
                per part data. Defaults to "<relative/absolute file path>:part<number>" when lazy loading, otherwise
                the part data itself is used.

    NOTE:
        - onload, parametrizer, and filter must take either one (data) or two (file path, data) arguments.
        - processor, marks, and ids (in callable form) additionally accept a three-argument form
          (idx, file path, data), where idx is the zero-based post-filter position of the item,
          counted continuously across all files matched by this data loader.
        - When reader is provided, its return value becomes the data passed to these callables.

    Examples:
    >>> @parametrize("data", "data.txt")
    >>> def test_example(data: list[str]):
    >>>     assert data in ["foo", "bar"]
    >>>
    >>> @parametrize(("file_path", "data"), "data.json")
    >>> def test_example2(file_path: Path, data: list[tuple[str, str]]):
    >>>     assert file_path.name == "data.json"
    >>>     assert data in [("key1", "value1"), ("key2", "value2")]
    >>>
    """
    return _setup_data_loader(
        cast(DataLoader, parametrize),
        fixture_names,
        path,
        lazy_loading=lazy_loading,
        reader=reader,
        onload=onload,
        parametrizer=parametrizer,
        filter=filter,
        processor=processor,
        marks=marks,
        ids=ids,
        read_options=read_options,
    )


@loader
def parametrize_dir(
    fixture_names: str | tuple[str, str],
    path: Path | str | Sequence[Path | str],
    /,
    *,
    lazy_loading: bool = True,
    recursive: bool = False,
    reader: Callable[[Path], Callable[..., Iterable[Any] | object]] | None = None,
    filter: Callable[[Path], bool] | None = None,
    processor: Callable[..., Any] | None = None,
    read_options: Callable[[Path], ReadOptions] | None = None,
    marks: PytestMarkType | Callable[[Path], PytestMarkType | None] | None = None,
    ids: Iterable[Any] | Callable[[Path], Any] | None = None,
) -> Callable[[Func], Func]:
    """A file loader that dynamically parametrizes the decorated test function with the content of files stored in the
    specified directory.

    :param fixture_names: Name(s) of the fixture(s) that will be made available to the test function. If a single
                          name is provided, the loaded data will be passed to that fixture. If two names are provided
                          either as a tuple or as a comma-separated string, the first fixture will receive the file
                          path, and the second will receive the loaded data.
    :param path: Path to the directory (or a list of directory paths, a glob pattern, or a list that mixes both) to
                 load files from. It can be either an absolute path or a path relative to one of the data directories.
                 When a relative path is provided, the loader searches for the nearest data directory containing a
                 matching directory and loads files from there.
                 When the provided path represents multiple directories, the loader concatenates files from all
                 directories in the order provided.
                 Environment variables are supported using the ``${VAR}`` or ``$VAR`` (or ``%VAR%`` for Windows) syntax.
    :param lazy_loading: If True, the plugin will defer the timing of file loading to the test setup phase. If False,
                         the data will be loaded during the test collection phase, which could cause a performance issue
    :param recursive: Recursively load files from all subdirectories of the given directory. Defaults to False.
                      NOTE: This option is ignored for directories matched by a glob pattern. Use ** for recursive
                            matching
    :param reader: A function to specify file readers to matching file paths.
    :param read_options: A function that returns the file read options (as a dict) the plugin passes to `open()` for
                         matching file paths. Supports only the mode, encoding, errors, and newline keys.
    :param filter: A function to filter file paths. Only the contents of matching file paths are included as the test
                   parameters.
    :param processor: A function to adjust the shape of each loaded file's data before passing it to the test function.
    :param marks: Pytest mark(s) for the loaded files. Accepts a single mark or a collection of marks applied uniformly
                  to all files, or a function that returns mark(s) for matching file paths.
    :param ids: Parameter IDs for the loaded files. Accepts an iterable of ID values or a function that returns an ID
                for matching file paths. Defaults to the relative or absolute file path when not provided.

    NOTE:
        - filter must take only one argument (file path).
        - reader, read_options, marks, and ids (in callable form) additionally accept a two-argument form
          (idx, file path), where idx is the zero-based post-filter position of the file, counted
          continuously across all directories matched by this data loader.
        - processor must take one (data), two (file path, data), or three (idx, file path, data) arguments,
          where idx is the zero-based post-filter position of the file, counted continuously across all
          directories matched by this data loader.

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
        filter=filter,
        processor=processor,
        marks=marks,
        ids=ids,
        reader_func=reader,
        read_options_func=read_options,
    )


def _setup_data_loader(
    loader: DataLoader,
    fixture_names: str | tuple[str, str],
    path: Path | str | Sequence[Path | str],
    /,
    *,
    lazy_loading: bool = True,
    recursive: bool = False,
    reader: Callable[..., Iterable[Any] | object] | None = None,
    read_options: ReadOptions | None = None,
    onload: Callable[..., Any] | None = None,
    parametrizer: Callable[..., Iterable[Any]] | None = None,
    filter: Callable[..., bool] | None = None,
    processor: Callable[..., Any] | None = None,
    marks: PytestMarkType | Callable[..., PytestMarkType | None] | None = None,
    ids: Iterable[Any] | Callable[..., Any] | None = None,
    reader_func: Callable[[Path], Callable[..., Iterable[Any] | object]] | None = None,
    read_options_func: Callable[[Path], ReadOptions] | None = None,
) -> Callable[[Func], Func]:
    """Set up a test function and inject loader attributes that are used by pytest_generate_tests hook"""
    validated_options = validate_loader_options(
        loader=loader,
        fixture_names=fixture_names,
        path=path,
        lazy_loading=lazy_loading,
        recursive=recursive,
        read_options=read_options,
        reader=reader,
        onload_func=onload,
        parametrizer_func=parametrizer,
        filter_func=filter,
        process_func=processor,
        reader_func=reader_func,
        read_options_func=read_options_func,
        marks=marks,
        ids=ids,
    )

    def wrapper(test_func: Func) -> Func:
        """Add attributes to the test function. This supports stacking multiple data loaders"""
        load_attrs = DataLoaderLoadAttrs(
            loader=loader,
            search_from=Path(inspect.getabsfile(test_func)),
            **validated_options,
        )
        existing_load_attrs: list[DataLoaderLoadAttrs] | None = getattr(test_func, PYTEST_DATA_LOADER_ATTRS, None)
        if existing_load_attrs is None:
            setattr(test_func, PYTEST_DATA_LOADER_ATTRS, [load_attrs])
        else:
            _check_fixture_name_collisions(test_func, existing_load_attrs, load_attrs)
            existing_load_attrs.append(load_attrs)
        return test_func

    return wrapper


def _check_fixture_name_collisions(
    test_func: Func,
    existing_load_attrs: list[DataLoaderLoadAttrs],
    new_load_attrs: DataLoaderLoadAttrs,
) -> None:
    """Raise ValueError if any fixture name in new_load_attrs collides with those already registered.

    :param test_func: The test function that stacks multiple data loaders
    :param existing_load_attrs: List of already-registered DataLoaderLoadAttrs for the function
    :param new_load_attrs: The newly created DataLoaderLoadAttrs to check for collisions
    """
    used_names: set[str] = set()
    for attrs in existing_load_attrs:
        used_names.update(attrs.fixture_names)
    collisions = used_names.intersection(new_load_attrs.fixture_names)
    if collisions:
        raise ValueError(
            f"Duplicate fixture name(s) {sorted(collisions)!r} in stacked data loaders on '{test_func.__name__}'. "
            f"Each stacked data loader must use unique fixture names."
        )
