pytest-data-loader
======================

[![PyPI](https://img.shields.io/pypi/v/pytest-data-loader)](https://pypi.org/project/pytest-data-loader/)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/pytest-data-loader.svg)](https://pypi.org/project/pytest-data-loader/)
[![test](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml?query=branch%3Amain)
[![Code style ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

`pytest-data-loader` is a `pytest` plugin that simplifies data-driven testing. It lets you load, transform, and 
parametrize test data directly from files and directories using simple decorators.



## Installation

```bash
pip install pytest-data-loader
```



## Quick Start

Load test data from a file and inject it directly into your test function.

```python
from pytest_data_loader import load


@load("data", "example.json")
def test_example(data):
    """
    example.json: '{"foo": 1, "bar": 2}'
    """
    assert isinstance(data, dict)
    assert data["foo"] == 1
```



## Usage

The plugin provides three data loaders — `@load`, `@parametrize`, and `@parametrize_dir` — available as decorators for 
loading test data.

- `@load`: Loads file content into a test
- `@parametrize`: Loads a file and parametrize a test by splitting its content into logical parts (e.g. lines, JSON items, etc.)
- `@parametrize_dir`: Loads files from a directory and parametrize a test for each file

Each data loader requires two positional arguments:
- `fixture_names`: Names of the fixtures injected into the test function
  - Single name: Injects the file data
  - Two names: Injects both the resolved file path and the file data
- `path`: An absolute path or a path relative to a data directory
  - When a relative path is given, the plugin searches upward from the test file for the **nearest** `data` directory 
  containing the target file or directory
  - For `@parametrize` and `@parametrize_dir`, this can also be a list of paths, a glob pattern, or a list that mixes 
both to aggregate data from multiple sources

> [!NOTE]
> If your data path is dynamic and unknown until runtime, use the `data_loader` fixture as a programmatic alternative to 
> `@load`. See [The data_loader Fixture](#the-data_loader-fixture)

> [!TIP]
> - The default data directory name can be customized using an INI option. See [INI Options](#ini-options)
> - Each data loader supports different optional keyword arguments to customize how the data is loaded. See 
> [Data Loading Pipeline](#data-loading-pipeline) and [Loader Options](#loader-options)
> - Each data loader can be stacked on a test function. See [Stacking Data Loaders](#stacking-data-loaders)



## Examples

Given you have the following project structure:
```
.(pytest rootdir)
├── data/               # shared data directory
│   ├── data1.json
│   ├── data2.txt
│   └── images/
│       ├── image.gif
│       ├── image.jpg
│       └── image.png
├── tests1/
│   └── test_something.py
└── tests2/
    ├── data/           # local data directory
    │   ├── data1.txt
    │   ├── data2.txt
    │   └── logos/
    │       ├── logo.jpg
    │       └── logo.png
    └── test_something_else.py
```

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
$ pytest tests1/test_something.py -v
================================ test session starts =================================
<snip>
collected 2 items                                                                              

tests1/test_something.py::test_something1[data1.json] PASSED                    [ 50%]
tests1/test_something.py::test_something2[data2.txt] PASSED                     [100%]

================================= 2 passed in 0.01s ==================================
```

> [!NOTE]
> - If both test files load `data1.json` and `data2.txt` using the same relative paths, the former is loaded from the 
> shared data directory, while the latter is resolved from each test file's **nearest** `data` directory. 
> This behavior applies to all loaders
> - For dynamic paths, use the `data_loader` fixture instead. See [The data_loader Fixture](#the-data_loader-fixture)


### 2. Parametrize file data — `@parametrize`
`@parametrize` is a file loader that dynamically parametrizes the decorated test function by splitting the loaded file
content into logical parts. Each part is passed to the test function as a separate parameter.

```python
# test_something.py

from pytest_data_loader import parametrize


@parametrize("data", "data1.json")
def test_something1(data):
    """
    data1.json: '{"foo": 1, "bar": 2}'
    """
    # parametrized as key–value pairs
    assert data in [("foo", 1), ("bar", 2)]


@parametrize(("file_path", "data"), "data2.txt")
def test_something2(file_path, data):
    """
    data2.txt: "line1\nline2\nline3"
    """
    # parametrized as lines
    assert file_path.name == "data2.txt"
    assert data in ["line1", "line2", "line3"]
```

```shell
$ pytest tests1/test_something.py -v
================================ test session starts =================================
<snip>
collected 5 items                                                                              

tests1/test_something.py::test_something1[data1.json:part1] PASSED              [ 20%]
tests1/test_something.py::test_something1[data1.json:part2] PASSED              [ 40%]
tests1/test_something.py::test_something2[data2.txt:part1] PASSED               [ 60%]
tests1/test_something.py::test_something2[data2.txt:part2] PASSED               [ 80%]
tests1/test_something.py::test_something2[data2.txt:part3] PASSED               [100%]

================================= 5 passed in 0.01s ==================================
```

> [!TIP]
> - You can apply your own logic by specifying the `parametrizer_func` loader option
> - By default, the plugin will apply the following logic for splitting file content:
>   - Text file: Each line
>   - JSON file:
>     - object: Each key–value pair in the object
>     - array: Each item in the array
>     - other types (string, number, boolean, null): The whole content as single data
>   - JSONL file: Each line (parsed as JSON)
>   - Binary file: Unsupported by default. You must provide a custom split logic as the `parametrizer_func` loader option


**Parametrize from multiple files**

You can pass a list of file paths, a glob pattern, or a list that mixes both to `@parametrize` to load and concatenate 
data from multiple files into a single parameter list:

```python
# test_something_else.py

from pytest_data_loader import parametrize


@parametrize("data", "*.txt")   # or ["data1.txt", "data2.txt"]
def test_something(data):
    """
    The glob pattern matches: 
      data1.txt: "line1\nline2"
      data2.txt: "line3\nline4"
    """
    assert data in ["line1", "line2", "line3", "line4"]
```

```shell
$ pytest tests2/test_something_else.py -v
================================ test session starts =================================
<snip>
collected 4 items

tests2/test_something_else.py::test_something[data1.txt:part1] PASSED           [ 25%]
tests2/test_something_else.py::test_something[data1.txt:part2] PASSED           [ 50%]
tests2/test_something_else.py::test_something[data2.txt:part1] PASSED           [ 75%]
tests2/test_something_else.py::test_something[data2.txt:part2] PASSED           [100%]

================================= 4 passed in 0.01s ==================================
```


### 3. Parametrize files in a directory — `@parametrize_dir`

`@parametrize_dir` is a directory loader that dynamically parametrizes the decorated test function with the contents
of files in the specified directory. Each file's content is passed to the test function as a separate parameter.

```python
# test_something.py

from pytest_data_loader import parametrize_dir


@parametrize_dir("data", "images")
def test_something(data):
    """
    images dir: contains 3 image files
    """
    # parametrized as files
    assert isinstance(data, bytes)
```

```shell
$ pytest tests1/test_something.py -v
================================ test session starts =================================
<snip>
collected 3 items                                                                              

tests1/test_something.py::test_something[images/image.gif] PASSED               [ 33%]
tests1/test_something.py::test_something[images/image.jpg] PASSED               [ 66%]
tests1/test_something.py::test_something[images/image.png] PASSED               [100%]

================================= 3 passed in 0.01s ==================================
```

> [!NOTE]
> - Use the `recursive=True` option to include files in subdirectories
> - Directory and file names starting with a dot (.) are considered hidden regardless of your platform. These are 
> automatically excluded from the parametrization



**Parametrize files from multiple directories**

You can pass a list of directory paths, a glob pattern, or a list that mixes both to `@parametrize_dir` to collect and 
concatenate files from multiple directories into a single parameter list:

```python
# test_something_else.py

from pytest_data_loader import parametrize_dir


@parametrize_dir("data", ["images", "logos"])
def test_something(data):
    """
    images dir: contains 3 image files
    logos dir: contains 2 logo files
    """
    assert isinstance(data, bytes)
```

```shell
$ pytest tests2/test_something_else.py -v
================================ test session starts =================================
<snip>
collected 5 items

tests2/test_something_else.py::test_something[images/image.gif] PASSED          [ 20%]
tests2/test_something_else.py::test_something[images/image.jpg] PASSED          [ 40%]
tests2/test_something_else.py::test_something[images/image.png] PASSED          [ 60%]
tests2/test_something_else.py::test_something[logos/logo.jpg] PASSED            [ 80%]
tests2/test_something_else.py::test_something[logos/logo.png] PASSED            [100%]

================================= 5 passed in 0.01s ==================================
```



## Stacking Data Loaders

All three data loaders — `@load`, `@parametrize`, and `@parametrize_dir` — can be stacked on a single test function. 
This allows you to declaratively compose complex, data-driven test scenarios while keeping test logic fully decoupled 
from data.

### Examples:

#### 1. Load multiple datasets
Stack multiple `@load` to inject independent datasets into a single test.

```python
from pytest_data_loader import load


@load("input_data", "input.json")
@load("expected_output", "expected.json")
def test_transformation_matches_expected_output(input_data, expected_output):
    """Verify that transforming input data produces the expected output."""
    assert do_something(input_data) == expected_output
```

#### 2. Generate a Cartesian product of test cases
Stack multiple `@parametrize` to automatically test all combinations.

```python
from pytest_data_loader import parametrize


@parametrize("user", "users.txt")
@parametrize("feature", "features.txt")
def test_user_feature_access_matrix(user, feature):
    """Validate access control for every user-feature combination."""
    assert can_access(user, feature)
```

#### 3. Combine shared context with parametrized inputs
Stack `@load` with `@parametrize` to test variable inputs with shared context.

```python
from pytest_data_loader import load, parametrize


@load("prices", "prices.json")
@parametrize("order", "orders.json")
def test_order_total_matches_expected(prices, order):
    """Validate that each order total is calculated correctly using the shared price catalog."""
    total = calculate_total(order, prices)
    assert total == order["expected_total"]
```

#### 4. Combine shared context with directory-based test scenarios
Stack `@load` with `@parametrize_dir` to test structured test cases with shared context.

```python
from pytest_data_loader import load, parametrize_dir


@load("banned_words", "banned_words.txt")
@parametrize_dir("comment", "user_comments/flagged")    # Each comment is stored as a .txt file
def test_flagged_comments_contain_banned_words(banned_words, comment):
    """Validate that flagged comments contain at least one banned word."""
    assert any(word in comment.lower() for word in banned_words)
```

> [!NOTE]
> - Fixture names must be unique across all stacked loaders on a test function
> - Stacking multiple `@parametrize` and/or `@parametrize_dir` decorators generates a Cartesian product of N × M test 
> cases (same behavior as `pytest.mark.parametrize`)
> - Files are loaded once per test function and cached across parametrized test cases

> [!TIP]
> When stacking data loaders, test IDs generated with the default parameter IDs may become less readable. Consider 
> explicitly specifying parameter IDs using the `id` option (`@load`) or the `id_func` option (`@parametrize`/`@parametrize_dir`)



## The `data_loader` Fixture

The plugin provides a function-scoped `data_loader` fixture as an alternative to `@load`. Use this fixture when the 
file path is not known until test runtime — for example, when it depends on another fixture, a parametrized value, or a 
CLI option, etc. The fixture provides a callable (an instance of the `DataLoaderFixture` class) that accepts a file 
path and returns the loaded data. It uses the same path resolution and loading logic as `@load`. Loader options like 
`file_reader`, `onload_func`, and read options are also supported and can be passed as keyword arguments.  
Below is an example where the file path depends on both a custom CLI option (`--env`) and parametrized test 
inputs, which is something the regular data loader decorators cannot support:

```python
import pytest
from pytest import FixtureRequest

from pytest_data_loader import DataLoaderFixture


@pytest.fixture(scope="session")
def env(request: FixtureRequest) -> str:
    """Target environment specified by the custom --env CLI option"""
    return request.config.getoption("--env")


@pytest.mark.parametrize("filename", ["case1.json", "case2.json"])
def test_env_specific_cases(data_loader: DataLoaderFixture, env: str, filename: str):
    # Construct path from a CLI option and parametrized value
    path = f"{env}/{filename}"
    case_data = data_loader(path)
    assert isinstance(case_data, dict)
```

> [!TIP]
> You can combine the `data_loader` fixture with `@load`, `@parametrize`, and `@parametrize_dir` in the same test 
> function. This is useful when some data paths are static while others are determined dynamically at runtime




## Lazy Loading

Lazy loading is enabled by default for all data loaders to improve efficiency, especially with large datasets. During 
test collection, pytest receives a lazy object instead of the actual data. The data is resolved only when it is needed 
during test setup.  
If you need to disable this behavior for a specific test, pass `lazy_loading=False` to the data loader.

> [!NOTE]
> Lazy loading for the `@parametrize` loader works slightly differently from other loaders. Since Pytest needs to know 
> the total number of parameters in advance, the plugin still needs to inspect the file data and split it once during 
> test collection phase. But once it's done, the split data will not be kept as parameter values and will be loaded 
> lazily later



## Data Loading Pipeline
Each data loader follows a simple pipeline where you can use loader options to hook into stages and filter or 
transform data before it reaches your test.

### @load
```text
file 
  → open                 # with read options
  → read and parse       # with file_reader()
  → transform            # with onload_func()
  → test(data)
```

### @parametrize
```text
file 
  → open                 # with read options 
  → read and parse       # with file_reader() 
  → transform            # with onload_func()
  → split                # with default or custom parametrizer_func()
    ↳ for each part:
      → filter           # with filter_func()
      → transform        # with process_func()
  → test(data₁, data₂, ...)
```

### @parametrize_dir
```text
directory 
  → collect files 
    ↳ for each file:
      → filter           # with filter_func()
      → open             # with read options
      → read and parse   # with file_reader_func()
      → transform        # with process_func()
  → test(file₁, file₂, ...)
```



## File Reader

### Built-in defaults

By default, the plugin reads and parses file content on loading as follows:
- `.json` — Parsed with `json.load`
- `.jsonl` — Each line is parsed as JSON object
- All other file types — Loads as raw text or binary content

### Customizing defaults

You can customize this behavior by specifying a file reader that accepts a file-like object returned by `open()`. 
This includes built-in readers, third-party library readers, and your own custom readers. File read options 
(e.g., `mode`, `encoding`, etc.) can also be provided and will be passed to `open()`.

Below are some common examples of file readers you might use:

| File type | Examples                                          | Notes                                            |
|-----------|---------------------------------------------------|--------------------------------------------------|
| .csv      | `csv.reader`, `csv.DictReader`, `pandas.read_csv` | `pandas.read_csv` requires `pandas`              |
| .yml      | `yaml.safe_load`, `yaml.safe_load_all`            | Requires `PyYAML`                                |
| .xml      | `xml.etree.ElementTree.parse`                     |                                                  |
| .toml     | `tomllib.load`                                    | `tomli.load` for Python <3.11 (Requires `tomli`) |
| .ini      | `configparser.ConfigParser().read_file`           |                                                  |
| .pdf      | `pypdf.PdfReader`                                 | Requires `pypdf`                                 |

This can be done either as a `conftest.py` level registration or as a test-level configuration. If both are done, the
test level configuration takes precedence over `conftest.py` level registration.
If multiple `conftest.py` files register a reader for the same file extension, the closest one from the current test
becomes effective.

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
> If read options are specified without a `file_reader`, the plugin uses the `conftest.py`-registered reader (if any)
> with those options. If a `file_reader` is specified without read options, no read options are applied

> [!TIP]
> - A file reader must take one argument (a file-like object returned by `open()`)
> - If you need to pass options to the file reader, use `lambda` function or a regular function  
> e.g. `file_reader=lambda f: csv.reader(f, delimiter=";")`
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

Each data loader supports different optional parameters you can use to change how your data is loaded.

### @load
- `lazy_loading`: Enable or disable lazy loading
- `file_reader`: A file reader the plugin should use to read the file data
- `onload_func`: A function to transform or preprocess loaded data before passing it to the test function
- `id`: The parameter ID for the loaded data. If not specified, the relative or absolute file path is used
- `**read_options`: File read options the plugin passes to `open()`. Supports only `mode`, `encoding`, `errors`, and 
`newline` options

> [!NOTE]
> `onload_func` must take either one (data) or two (file path, data) arguments. When `file_reader` is provided, the 
data is the reader object itself


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
its return value becomes the data passed to loader functions


### @parametrize_dir
- `lazy_loading`: Enable or disable lazy loading
- `recursive`: Recursively load files from all subdirectories of the given directory. Defaults to `False`. 
This option is ignored for glob patterns. Use `**` instead for recursive matching
- `file_reader_func`: A function that determines the file reader for each file path
- `filter_func`: A function to filter file paths. Only the contents of matching file paths are included as the test 
parameters
- `process_func`: A function to adjust the shape of each loaded file's data before passing it to the test function
- `marker_func`: A function to apply Pytest marks to matching file paths
- `id_func`: A function to generate a parameter ID from each file path
- `read_option_func`: A function that returns file read options (as a dict) for matching file paths. The returned dict 
may contain only `mode`, `encoding`, `errors`, and `newline` keys, which are passed to `open()`

> [!NOTE]
> - `process_func` must take either one (data) or two (file path, data) arguments
> - `file_reader_func`, `filter_func`, `marker_func`, `id_func`, and `read_option_func` must take only one argument (file path)



## INI Options

### `data_loader_dir_name`
The base directory name to load test data from. When a relative file or directory path is provided to a data loader, 
it is resolved relative to the nearest matching data directory in the directory tree.  
Plugin default: `data`

### `data_loader_root_dir`
Absolute or relative path to the project's root directory. By default, the search is limited to 
within pytest's rootdir, which may differ from the project's top-level directory. Setting this option allows data 
directories located outside pytest's rootdir to be found. 
Environment variables are supported using the `${VAR}` or `$VAR` (or `%VAR%` on Windows) syntax.
Plugin default: Pytest rootdir (`config.rootpath`)

### `data_loader_strip_trailing_whitespace`
Automatically remove trailing whitespace characters when loading text data.  
Plugin default: `true`
