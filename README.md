pytest-data-loader
======================

[![PyPI](https://img.shields.io/pypi/v/pytest-data-loader)](https://pypi.org/project/pytest-data-loader/)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/pytest-data-loader.svg)](https://pypi.org/project/pytest-data-loader/)
[![test](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/yugokato/pytest-data-loader/actions/workflows/test.yml?query=branch%3Amain)
[![Code style ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

`pytest-data-loader` is a `pytest` plugin for loading test data from files to facilitate data-driven testing.  
In addition to loading data from a single file, it supports dynamic test parametrization by splitting file data into 
parts or by loading multiple files from a directory.


## Installation

```bash
pip install pytest-data-loader
```



## Quick Start

```python
from pytest_data_loader import load

# Loads and injects data from data/example.json as the "data" fixture
@load("data", "example.json")
def test_example(data):
    """
    example.json: {"foo": 1, "bar": 2}
    """
    assert "foo" in data
```



## Usage

The plugin provides three data loaders — `@load`, `@parametrize`, and `@parametrize_dir` — available as decorators for 
loading test data. As a common design, each loader takes two positional arguments: 

- `fixture_names`: Name(s) of the fixture(s) that will be made available to the test function. It supports either one
                   (receiving file data) or two (receiving file path and file data) fixture names
- `relative_path`: File or directory path relative to one of the base "data" loader directories to load test data 
                   from. The plugin will search for the closest "data" directory from the test file's directory and up 
                   towards the Pytest root directory

Additionally, each loader supports different optional keyword arguments to customize how the data is loaded. See the 
"Loader Options" section for details.



## Examples:

Given you have the following project structure:
```
.(pytest rootdir)
├── data/
│   ├── data1.json
│   ├── data2.txt
│   └── images/
│       ├── image1.gif
│       ├── image2.jpg
│       └── image3.png
├── tests1/
│   ├── data/
│   │   ├── data1.txt
│   │   └── data2.txt
│   └── test_something_else.py
└── test_something.py
```
The plugin searches for a `data` directory relative to the test file to locate data files.

### 1. Load file data (`@load`)
`@load` is a file loader that loads the file content and passes it to the test function.

```python
from pytest_data_loader import load


@load("data", "data1.json")
def test_something1(data):
    """
    This test loads the content of data/data1.json. The parsed JSON data is accessible through the specified 
    fixture argument, `data` in this example.
    """
    ...

@load(("file_path", "data"), "data2.txt")
def test_something2(file_path, data):
    """
    This test loads the content of data/data2.txt. The file path and file content are accessible through the 
    specified fixture arguments, `file_path` and `data` in this example.
    """
```

> [!NOTE]
> If both `./test_something.py` and `./tests1/test_something_else.py` happen to have the above same loader definitions, 
> the first test function will load `./data/data1.json` for both test files, and the second test function will load 
> `data2.txt` from each test file's **nearest** `data` directory. This ensures that each test file loads data from its 
> nearest data directory.  
> This behavior applies to all loaders.


### 2. Parametrize file data (`@parametrize`)
`@parametrize` is a file loader that dynamically parametrizes the decorated test function by splitting the loaded file 
content into logical parts. The test function will then receive the part data as loaded data for the current test.

```python
from pytest_data_loader import parametrize


@parametrize("data", "data1.json")
def test_something1(data):
    """
    This test will be dynamically parametrized with each key–value pair in a JSON object or each item in a JSON array, 
    depending on the data stored in data1.json.
    The parametrized data is accessible through the specified fixture argument, `data` in this example.
    """
    ...

@parametrize(("file_path", "data"), "data2.txt")
def test_something2(file_path, data):
    """
    This test will be dynamically parametrized with each text line from data2.txt. 
    The file path and each parametrized text line are accessible through the specified fixture arguments, 
    `file_path` and `data` in this example.
    """
    ...
```
> [!TIP]
> - By default, the plugin will apply the following logic for splitting file content: 
>   - Text file: Each line in a file
>   - JSON file:
>     - object: Each key–value pair in the object
>     - array: Each item in the array
>     - other types (string, number, boolean, null): The whole content as a single chunk
>   - Binary file: Unsupported. Requires specifying a custom split logic as the `parametrizer_func` loader option 
> - You can apply your own logic by specifying the `parametrizer_func` loader option


### 3. Parametrize files in a directory (`@parametrize_dir`)

`@parametrize_dir` is a file loader that dynamically parametrizes the decorated test function with the contents of the 
files stored in the specified directory. The test function will then receive the content of each file as loaded data 
for the current test.

```python
from pytest_data_loader import parametrize_dir


@parametrize_dir("data", "images")
def test_something(data):
    """
    This test will be dynamically parametrized with each image file in the `images` directory.
    """
    ...
```
> [!NOTE]
> File names starting with a dot (.) are considered hidden files regardless of your platform. 
> These files are automatically excluded from the parametrization.  



## Lazy Loading

Lazy loading is enabled by default for all loaders to improve performance, especially with large datasets. During the 
test collection phase, Pytest receives a lazy object as a test parameter instead of the actual data. The data is 
resolved only when it is needed during test setup.    
If you need to disable this behavior for a specific test for some reason, you can specify the `lazy_loading=False` 
option on the loader.

> [!NOTE]
> Lazy loading in the `@parametrize` loader works slightly differently from other loaders. Since Pytest needs to know 
> the total number of parameters in advance, the plugin may still need to load the file data once and split during test 
> collection phase, depending on the file type and the specified loader options. But once it's done, those part data 
> will not be kept as parameter values and will be loaded lazily later.



## Loader Options

Each loader supports different optional parameters you can use to change how your data is loaded.
### @load
- `lazy_loading`: Enable or disable lazy loading
- `force_binary`: Force the file to be read in binary mode
- `onload_func`: A function to transform or preprocess loaded data before passing it to the test function
- `id`: An ID for the loaded data. The file name is used if not specified

### @parametrize
- `lazy_loading`: Enable or disable lazy loading
- `onload_func`: A function to adjust the shape of the loaded data before splitting into parts
- `parametrizer_func`: A function to customize how the loaded data should be split
- `filter_func`: A function to filter the split data parts. Only matching parts are included as test parameters
- `process_func`: A function to adjust the shape of each split data before passing it to the test function
- `id_func`: A function to generate a parameter ID for each test parameter, supported only when lazy_loading is `False`

### @parametrize_dir
- `lazy_loading`: Enable or disable lazy loading
- `force_binary`: Force each file to be read in binary mode
- `filter_func`: A function to filter file paths. Only the contents of matching file paths are included as the test 
parameters
- `process_func`: A function to adjust the shape of each loaded file's data before passing it to the test function



## INI Options

### `data_loader_dir_name`
A base directory name to load test data from. The file or directory path specified to a loader is considered a 
relative path to one of these base directories in the directory tree.  
Plugin default: `data`

### `data_loader_strip_trailing_whitespace`
Automatically remove trailing whitespace characters when loading text data.  
Plugin default: `true`
