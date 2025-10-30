pytest-data-loader
======================

[![PyPI](https://img.shields.io/pypi/v/pytest-data-loader)](https://pypi.org/project/pytest-data-loader/)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/pytest-data-loader.svg)](https://pypi.org/project/pytest-data-loader/)
[![test](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml?query=branch%3Amain)
[![Code style ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

`pytest-data-loader` is a `pytest` plugin that simplifies loading test data from files for data-driven testing.  
It supports not only loading a single file, but also dynamic test parametrization either by splitting file data into 
parts or by loading multiple files from a directory.


## Installation

```bash
pip install pytest-data-loader
```



## Quick Start

```python
from pytest_data_loader import load


@load("data", "example.json")
def test_example(data):
    """
    Loads data/example.json and injects it as the "data" fixture.
    
    example.json: '{"foo": 1, "bar": 2}'
    """
    assert "foo" in data
```

## Usage

The plugin provides three data loaders — `@load`, `@parametrize`, and `@parametrize_dir` — available as decorators for 
loading test data. Each loader takes two positional arguments: 

- `fixture_names`: Name(s) of the fixture(s) that will be made available to the test function. It supports either one
                   (receiving file data) or two (receiving file path and file data) fixture names
- `path`: Path to the file or directory to load data from. It can be either an absolute path or a path relative to one
          of the project's data directories. When a relative path is provided, the plugin searches upward from the 
          test file's directory toward the Pytest root directory to find the nearest data directory containing the 
          target file.

Additionally, each loader supports different optional keyword arguments to customize how the data is loaded. See 
[Loader Options](#loader-options) section for details.



## Examples:

Given you have the following project structure:
```
.(pytest rootdir)
├── data/
│   ├── data1.json
│   ├── data2.txt
│   └── images/
│       ├── image.gif
│       ├── image.jpg
│       └── image.png
├── tests1/
│   ├── data/
│   │   ├── data1.txt
│   │   └── data2.txt
│   └── test_something_else.py
└── test_something.py
```
The plugin searches for a data directory (default name: `data`) that contains the specified file or directory.

### 1. Load file data — `@load`
`@load` is a file loader that loads the file content and passes it to the test function.

```python
# test_something.py

from pytest_data_loader import load


@load("data", "data1.json")
def test_something1(data):
    """
    data1.json: '{"foo": 1, "bar": 2}'
    """
    assert data == {"foo": 1, "bar": 2}


@load(("file_path", "data"), "data2.txt")
def test_something2(file_path, data):
    """
    data2.txt: "line1\nline2\nline3"
    """
    assert file_path.name == "data2.txt"
    assert data == "line1\nline2\nline3"
```

```shell
$ pytest test_something.py -v
================================ test session starts =================================
<snip>
collected 2 items                                                                              

tests/test_something.py::test_something1[data1.json] PASSED                     [ 50%]
tests/test_something.py::test_something2[data2.txt] PASSED                      [100%]

================================= 2 passed in 0.01s ==================================
```

> [!NOTE]
> If both `./test_something.py` and `./tests1/test_something_else.py` happen to have the above same loader definitions, 
> the first test function will load `./data/data1.json` for both test files, and the second test function will load 
> `data2.txt` from each test file's **nearest** `data` directory. This ensures that each test file loads data from its 
> nearest data directory.  
> This behavior applies to all loaders.


### 2. Parametrize file data — `@parametrize`
`@parametrize` is a file loader that dynamically parametrizes the decorated test function by splitting the loaded file 
content into logical parts. The test function will then receive the part data as loaded data for the current test.

```python
# test_something.py

from pytest_data_loader import parametrize


@parametrize("data", "data1.json")
def test_something1(data):
    """
    data1.json: '{"foo": 1, "bar": 2}'
    """
    assert data in [("foo", 1), ("bar", 2)]


@parametrize(("file_path", "data"), "data2.txt")
def test_something2(file_path, data):
    """
    data2.txt: "line1\nline2\nline3"
    """
    assert file_path.name == "data2.txt"
    assert data in ["line1", "line2", "line3"]
```

```shell
$ pytest test_something.py -v
================================ test session starts =================================
<snip>
collected 5 items                                                                              

tests/test_something.py::test_something1[data1.json:part1] PASSED               [ 20%]
tests/test_something.py::test_something1[data1.json:part2] PASSED               [ 40%]
tests/test_something.py::test_something2[data2.txt:part1] PASSED                [ 60%]
tests/test_something.py::test_something2[data2.txt:part2] PASSED                [ 80%]
tests/test_something.py::test_something2[data2.txt:part3] PASSED                [100%]

================================= 5 passed in 0.01s ==================================
```

> [!TIP]
> - You can apply your own logic by specifying the `parametrizer_func` loader option
> - By default, the plugin will apply the following logic for splitting file content: 
>   - Text file: Each line in the file
>   - JSON file:
>     - object: Each key–value pair in the object
>     - array: Each item in the array
>     - other types (string, number, boolean, null): The whole content as single data
>   - Binary file: Unsupported. Requires specifying a custom split logic as the `parametrizer_func` loader option 


### 3. Parametrize files in a directory — `@parametrize_dir`

`@parametrize_dir` is a directory loader that dynamically parametrizes the decorated test function with the 
contents of the files stored in the specified directory. The test function will then receive the content of each file as loaded data 
for the current test.

```python
# test_something.py

from pytest_data_loader import parametrize_dir


@parametrize_dir("data", "images")
def test_something(data):
    """
    images dir: contains 3 image files
    """
    assert isinstance(data, bytes)
```

```shell
$ pytest test_something.py -v
================================ test session starts =================================
<snip>
collected 3 items                                                                              

tests/test_something.py::test_something[image.gif] PASSED                       [ 33%]
tests/test_something.py::test_something[image.jpg] PASSED                       [ 66%]
tests/test_something.py::test_something[image.png] PASSED                       [100%]

================================= 3 passed in 0.01s ==================================
```

> [!NOTE]
> File names starting with a dot (.) are considered hidden files regardless of your platform. 
> These files are automatically excluded from the parametrization.  



## Lazy Loading

Lazy loading is enabled by default for all data loaders to improve efficiency, especially with large datasets.  During 
test collection, pytest receives a lazy object as a test parameter instead of the actual data. The data is resolved 
only when it is needed during test setup.    
If you need to disable this behavior for a specific test, pass `lazy_loading=False` to the data loader.

> [!NOTE]
> Lazy loading for the `@parametrize` loader works slightly differently from other loaders. Since Pytest needs to know 
> the total number of parameters in advance, the plugin still needs to inspect the file data and split it once during 
> test collection phase. But once it's done, those part data will not be kept as parameter values and will be loaded 
> lazily later.



## File Reader

You can specify a file reader the plugin should use when reading the file data, with/without file read options that 
will be passed to `open()`. This can be done either as a `conftest.py` level registration or as a test-level 
configuration. If both are done, the test level configuration takes precedence over `conftest.py` level registration.  
If multiple `conftest.py` files register a reader for the same file extension, the closest one from the current test 
becomes effective.  

As examples, here are some of the common readers you could use:

| File type | Reader                                            | Notes                                             |
|-----------|---------------------------------------------------|---------------------------------------------------|
| .json     | `json.load`                                       | The plugin automatically uses this by default     |
| .csv      | `csv.reader`, `csv.DictReader`, `pandas.csv_read` | `pandas.csv_read` requires `pandas`               |
| .yml      | `yaml.safe_load`, `yaml.safe_load_all`            | Requires `PyYAML`                                 |
| .xml      | `xml.etree.ElementTree.parse`                     |                                                   |
| .toml     | `tomllib.load`                                    | `tomli.load` for Python <3.11  (Requires `tomli`) |
| .ini      | `configparser.ConfigParser().read_file`           |                                                   |
| .pdf      | `pypdf.PdfReader`                                 | Requires `pypdf`                                  |

Here are some examples of loading a CSV file using the built-in CSV readers with file read options:

### 1. `conftest.py` level registration

Register a file reader using `pytest_data_loader.register_reader()`. It takes a file extension and a file reader as 
positional arguments, and file read options as keyword arguments.

```python
# conftest.py

import csv

import pytest_data_loader


pytest_data_loader.register_reader(".csv", csv.reader, newline="")
```

The registered file reader automatically applies to all tests located in the same directory and any of its subdirectories.

```python
# test_something.py

from pytest_data_loader import load


@load("data", "data.csv")
def test_something(data):
    """Load CSV file with registered file reader"""
    for row in data:
        assert isinstance(row, list)
```


### 2. Per-test configuration with loader options

Specify a file reader with the `file_reader` loader option. This applies only to the configured test, and overrides the 
one registered in `conftest.py`. 

```python
# test_something.py

import csv

from pytest_data_loader import load, parametrize


@load("data", "data.csv", file_reader=csv.reader, encoding="utf-8-sig", newline="")
def test_something1(data):
    """Load CSV file with csv.reader reader"""
    for row in data:
        assert isinstance(row, list)


@parametrize("data", "data.csv", file_reader=csv.DictReader, encoding="utf-8-sig", newline="")
def test_something2(data):
    """Parametrize CSV file data with csv.DictReader reader"""
    assert isinstance(data, dict)
```

> [!NOTE]
> If only read options are specified without a `file_reader` in a loader, the plugin will search for an existing file 
> reader registered in `conftest.py` if there is any, and applies it with the new read options for the test. But if 
> only a `file_reader` is specified with no read options in a loder, no read options will be applied.

> [!TIP]
> - A file reader must take one argument (a file-like object returned by `open()`)
> - If you need to pass options to the file reader, use `lambda` function or a regular function.  
> eg. `file_reader=lambda f: csv.reader(f, delimiter=";")`
> - You can adjust the final data the test function receives using loader functions. For example, 
> the following code will parametrize the test with the text data from each PDF page   
>  ```python
>  @parametrize(
>      "data", 
>      "test.pdf", 
>      file_reader=pypdf.PdfReader, 
>      parametrizer_func=lambda r: r.pages,
>      process_func=lambda p: p.extract_text().rstrip(),
>      mode="rb"
>  )
>  def test_something(data: str):
>      ...
>  ```



## Loader Options

Each loader supports different optional parameters you can use to change how your data is loaded.

### @load
- `lazy_loading`: Enable or disable lazy loading
- `file_reader`: A file reader the plugin should use to read the file data
- `onload_func`: A function to transform or preprocess loaded data before passing it to the test function
- `id`: The parameter ID for the loaded data. The file name is used if not specified
- `**read_options`: File read options the plugin passes to `open()`. Supports only `mode`, `encoding`, `errors`, and 
`newline` options

> [!NOTE]
> `onload_func` must take either one (data) or two (file path, data) arguments. When `file_reader` is provided, the data 
is the reader object itself.


### @parametrize
- `lazy_loading`: Enable or disable lazy loading
- `file_reader`: A file reader the plugin should use to read the file data
- `onload_func`: A function to adjust the shape of the loaded data before splitting into parts
- `parametrizer_func`: A function to customize how the loaded data should be split
- `filter_func`: A function to filter the split data parts. Only matching parts are included as test parameters
- `process_func`: A function to adjust the shape of each split data before passing it to the test function
- `marker_func`: A function to apply Pytest marks to matching part data
- `id_func`: A function to generate a parameter ID for each part data
- `**read_options`: File read options the plugin passes to `open()`. Supports only `mode`, `encoding`, `errors`, 
and `newline` options

> [!NOTE]
> Each loader function must take either one (data) or two (file path, data) arguments. When `file_reader` is provided, 
the data is the reader object itself.


### @parametrize_dir
- `lazy_loading`: Enable or disable lazy loading
- `file_reader_func`: A function to specify file readers to matching file paths
- `filter_func`: A function to filter file paths. Only the contents of matching file paths are included as the test 
parameters
- `process_func`: A function to adjust the shape of each loaded file's data before passing it to the test function
- `marker_func`: A function to apply Pytest marks to matching file paths
- `read_option_func`: A function to specify file read options the plugin passes to `open()` to matching file paths. 
Supports only `mode`, `encoding`, `errors`, and `newline` options. It must return these options as a dictionary

> [!NOTE]
> - `process_func` must take either one (data) or two (file path, data) arguments
> - `file_reader_func`, `filter_func`, `marker_func`, and `read_option_func` must take only one argument (file path)



## INI Options

### `data_loader_dir_name`
The base directory name to load test data from. When a relative file or directory path is provided to a data loader, 
it is resolved relative to the nearest matching data directory in the directory tree.  
Plugin default: `data`

### `data_loader_root_dir`
Absolute or relative path to the project's root directory. By default, the search is limited to 
within pytest's rootdir, which may differ from the project's top-level directory. Setting this option allows data 
directories located outside pytest's rootdir to be found. 
Environment variables are supported using the `${VAR}` or `$VAR` (or `%VAR%` for windows) syntax.  
Plugin default: Pytest rootdir (`config.rootpath`)

### `data_loader_strip_trailing_whitespace`
Automatically remove trailing whitespace characters when loading text data.  
Plugin default: `true`
