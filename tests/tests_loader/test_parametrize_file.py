import json

from pytest import FixtureRequest

from pytest_data_loader import parametrize
from tests.tests_loader.helper import (
    ABS_PATH_LOADER_DIR,
    PATH_JPEG_FILE,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_NESTED_OBJECT,
    PATH_JSON_FILE_OBJECT,
    PATH_JSON_FILE_SCALAR,
    PATH_TEXT_FILE,
    get_parametrized_test_idx,
)

# NOTE:
# - lazy_loading option is separately tested in another test using pytester
# - This file covers 3 types of data types the plugin handles differently: text file, json file, and binary file


# Text file
@parametrize("data", PATH_TEXT_FILE)
def test_parametrize_text_file_with_no_options(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with no options using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"line{idx}"


@parametrize("data", PATH_TEXT_FILE, onload_func=lambda d: "# " + d)
def test_parametrize_text_file_with_onload_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the onload_func option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    if idx == 0:
        assert data == f"# line{idx}"
    else:
        assert data == f"line{idx}"


@parametrize("data", PATH_TEXT_FILE, parametrizer_func=lambda d: ((d[i : i + 3]).ljust(3) for i in range(0, len(d), 3)))
def test_parametrize_text_file_with_parametrizer_func(data: str) -> None:
    """Test @parametrize loder with the parametrizer_func option using text file"""
    assert isinstance(data, str)
    assert len(data) == 3


@parametrize("data", PATH_TEXT_FILE, filter_func=lambda d: d.endswith("1"))
def test_parametrize_text_file_with_filter_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the filter_func option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert idx == 0
    assert data == "line1"


@parametrize("data", PATH_TEXT_FILE, process_func=lambda d: "# " + d)
def test_parametrize_text_file_with_process_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the process_func option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"# line{idx}"


@parametrize(
    "data",
    PATH_TEXT_FILE,
    id_func=lambda d: repr("#" + d),
    # id_func is not supported when lazy_loading=True
    lazy_loading=False,
)
def test_parametrize_text_file_with_id_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the id_func option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert request.node.name.endswith(f"['#line{idx}']")


# JSON file
@parametrize("data", PATH_JSON_FILE_SCALAR)
def test_parametrize_json_file_scalar(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with no options using JSON file (object)"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert idx == 0
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_SCALAR).read_text())


@parametrize("data", PATH_JSON_FILE_ARRAY)
def test_parametrize_json_file_array(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with no options using JSON file (array)"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"item{idx}"


@parametrize("data", PATH_JSON_FILE_OBJECT)
def test_parametrize_json_object(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loder with no options using JSON file (object)"""
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    assert data == (f"key{idx}", f"value{idx}")


@parametrize("data", PATH_JSON_FILE_NESTED_OBJECT, onload_func=lambda d: d["dev"])
def test_parametrize_json_with_onload_func(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loder with the onload_func using JSON file"""
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    assert data == (f"key{idx}", f"dev_value{idx}")


@parametrize("data", PATH_JSON_FILE_OBJECT, parametrizer_func=lambda d: d.keys())
def test_parametrize_json_with_parametrizer_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the parametrizer_func using JSON file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"key{idx}"


@parametrize("data", PATH_JSON_FILE_ARRAY, filter_func=lambda d: d.endswith("1"))
def test_parametrize_json_with_filter_func(data: str) -> None:
    """Test @parametrize loder with the filter_func using JSON file"""
    assert isinstance(data, str)
    assert data == "item1"


@parametrize("data", PATH_JSON_FILE_OBJECT, process_func=lambda d: d[0])
def test_parametrize_json_with_process_func(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loder with the process_func using JSON file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"key{idx}"


@parametrize(
    "data",
    PATH_JSON_FILE_OBJECT,
    id_func=lambda d: repr(d[0]),
    # id_func is not supported when lazy_loading=True
    lazy_loading=False,
)
def test_parametrize_json_with_id_func(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loder with the id_func using JSON file"""
    assert isinstance(data, tuple)
    assert request.node.name.endswith(f"[{data[0]!r}]")


# Binary files
@parametrize("data", PATH_JPEG_FILE, parametrizer_func=lambda d: _split_jpeg(d))
def test_parametrize_binary_file_with_parametrizer_func(request: FixtureRequest, data: bytes) -> None:
    """Test @parametrize loder with the parametrizer_func using binary file"""
    assert isinstance(data, bytes)
    idx = get_parametrized_test_idx(request, "data")
    assert idx in range(3)
    if idx == 0:
        # Chunk 0 should start with SOI
        assert data.startswith(b"\xff\xd8")
    elif idx == 1:
        # Second chunk must start with SOS
        assert data.startswith(b"\xff\xda")
    else:
        # Last chunk must be EOI
        assert data == b"\xff\xd9"


@parametrize(
    "data",
    PATH_JPEG_FILE,
    parametrizer_func=lambda d: [d],  # single param
    id_func=lambda d: repr(d[:5]),
    # id_func is not supported when lazy_loading=True
    lazy_loading=False,
)
def test_parametrize_binary_file_with_id_func(request: FixtureRequest, data: bytes) -> None:
    """Test @parametrize loder with the id_func using binary file"""
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()
    # Pytest internally applies repr() for the ID, which double escapes the ID value the plugin specifies for bytes.
    # For testing purpose, we adjust the nodeid value pytest holds to match with what we specified
    assert request.node.nodeid.encode("utf-8").decode("unicode_escape").endswith(f"[{data[:5]!r}]")


def _truncate_binary(data: bytes, length: int = 5) -> bytes:
    """Truncate binary data for display purposes"""
    if len(data) <= length:
        return data
    return data[:length] + b"..."


def _split_jpeg(data: bytes) -> list[bytes]:
    """Split a JPEG file into 3 chunks: header, scan data, and end of image

    Note: This was generated by ChatGPT
    """
    # Find Start of Scan (SOS) marker: 0xFFDA
    sos_index = data.find(b"\xff\xda")
    # Find End of Image (EOI) marker: 0xFFD9
    eoi_index = data.rfind(b"\xff\xd9")

    if sos_index == -1 or eoi_index == -1:
        raise ValueError("Not a valid JPEG file")

    # Chunk 1: Header (everything before SOS)
    header = data[:sos_index]
    # Chunk 2: Scan data (from SOS to EOI, exclusive)
    scan_data = data[sos_index:eoi_index]
    # Chunk 3: End of image
    end = data[eoi_index:]

    return [header, scan_data, end]
