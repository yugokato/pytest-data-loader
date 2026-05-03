import json

import pytest
from pytest import FixtureRequest

from pytest_data_loader import parametrize
from tests.paths import (
    ABS_PATH_LOADER_DIR,
    PATH_JPEG_FILE,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_NESTED_OBJECT,
    PATH_JSON_FILE_OBJECT,
    PATH_JSON_FILE_SCALAR,
    PATH_TEXT_FILE,
)

from .helper import get_parametrized_test_idx

pytestmark = pytest.mark.loaders

# NOTE:
# - lazy_loading option is separately tested in another test using pytester
# - This file covers 3 types of data types the plugin handles differently:
#   - text file (non-structured file)
#   - json file (structured file)
#   - binary file


# Text file
@parametrize("data", PATH_TEXT_FILE)
def test_parametrize_text_file_with_no_options(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with no options using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"line{idx}"


@parametrize("data", PATH_TEXT_FILE, onload=lambda d: "# " + d)
def test_parametrize_text_file_with_onload(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the onload option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    if idx == 0:
        assert data == f"# line{idx}"
    else:
        assert data == f"line{idx}"


@parametrize("data", PATH_TEXT_FILE, parametrizer=lambda d: ((d[i : i + 3]).ljust(3) for i in range(0, len(d), 3)))
def test_parametrize_text_file_with_parametrizer(data: str) -> None:
    """Test @parametrize loader with the parametrizer option using text file"""
    assert isinstance(data, str)
    assert len(data) == 3


@parametrize("data", PATH_TEXT_FILE, filter=lambda d: d.endswith("1"))
def test_parametrize_text_file_with_filter(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the filter option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert idx == 0
    assert data == "line1"


@parametrize("data", PATH_TEXT_FILE, processor=lambda d: "# " + d)
def test_parametrize_text_file_with_processor(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the processor option using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"# line{idx}"


@parametrize("data", PATH_TEXT_FILE, marks=lambda d: pytest.mark.foo if d.endswith("0") else None)
def test_parametrize_text_file_with_marks_callable(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the marks option (callable) using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    marker = request.node.get_closest_marker("foo")
    if idx == 0:
        assert marker
    else:
        assert marker is None


@parametrize("data", PATH_TEXT_FILE, marks=pytest.mark.foo)
def test_parametrize_text_file_with_marks_single(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the marks option (single mark applied to all)"""
    assert isinstance(data, str)
    assert request.node.get_closest_marker("foo")


@parametrize("data", PATH_TEXT_FILE, marks=[pytest.mark.foo, pytest.mark.bar])
def test_parametrize_text_file_with_marks_multi(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the marks option (a collection of marks applied to all)"""
    assert isinstance(data, str)
    mark_names = {m.name for m in request.node.own_markers}
    assert "foo" in mark_names
    assert "bar" in mark_names


@parametrize("data", PATH_TEXT_FILE, ids=lambda d: repr("#" + d))
def test_parametrize_text_file_with_ids_callable(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the ids option (callable) using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert request.node.name.endswith(f"['#line{idx}']")


@parametrize("data", PATH_TEXT_FILE, ids=["id0", "id1", "id2"])
def test_parametrize_text_file_with_ids_sequence(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the ids option (a sequence of IDs) using text file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert request.node.name.endswith(f"[id{idx}]")


# JSON file
@parametrize("data", PATH_JSON_FILE_SCALAR)
def test_parametrize_json_file_scalar(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with no options using JSON file (object)"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert idx == 0
    assert data == json.loads((ABS_PATH_LOADER_DIR / PATH_JSON_FILE_SCALAR).read_text())


@parametrize("data", PATH_JSON_FILE_ARRAY)
def test_parametrize_json_file_array(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with no options using JSON file (array)"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"item{idx}"


@parametrize("data", PATH_JSON_FILE_OBJECT)
def test_parametrize_json_object(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loader with no options using JSON file (object)"""
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    assert data == (f"key{idx}", f"value{idx}")


@parametrize("data", PATH_JSON_FILE_NESTED_OBJECT, onload=lambda d: d["dev"])
def test_parametrize_json_with_onload(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loader with the onload using JSON file"""
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    assert data == (f"key{idx}", f"dev_value{idx}")


@parametrize("data", PATH_JSON_FILE_OBJECT, parametrizer=lambda d: d.keys())
def test_parametrize_json_with_parametrizer(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the parametrizer using JSON file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"key{idx}"


@parametrize("data", PATH_JSON_FILE_ARRAY, filter=lambda d: d.endswith("1"))
def test_parametrize_json_with_filter(data: str) -> None:
    """Test @parametrize loader with the filter using JSON file"""
    assert isinstance(data, str)
    assert data == "item1"


@parametrize("data", PATH_JSON_FILE_OBJECT, processor=lambda d: d[0])
def test_parametrize_json_with_processor(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with the processor using JSON file"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"key{idx}"


@parametrize("data", PATH_JSON_FILE_OBJECT, marks=lambda d: pytest.mark.foo if d[0].endswith("0") else None)
def test_parametrize_json_with_marks(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loader with the marks option using JSON file"""
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    marker = request.node.get_closest_marker("foo")
    if idx == 0:
        assert marker
    else:
        assert marker is None


@parametrize("data", PATH_JSON_FILE_OBJECT, ids=lambda d: repr(d[0]))
def test_parametrize_json_with_ids_callable(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loader with the ids option (callable) using JSON file"""
    assert isinstance(data, tuple)
    assert request.node.name.endswith(f"[{data[0]!r}]")


@parametrize("data", PATH_JSON_FILE_OBJECT, ids=["a", "b", "c"])
def test_parametrize_json_with_ids_sequence(request: FixtureRequest, data: tuple[str, str]) -> None:
    """Test @parametrize loader with the ids option (a sequence of IDs) using JSON file.

    Uses the JSON structured-file code path where IDs are stored eagerly in LazyLoadedPartData.meta.
    """
    assert isinstance(data, tuple)
    idx = get_parametrized_test_idx(request, "data")
    expected_ids = ["a", "b", "c"]
    assert request.node.name.endswith(f"[{expected_ids[idx]}]")


@parametrize("data", [PATH_TEXT_FILE, PATH_JSON_FILE_ARRAY])
def test_parametrize_multi_files(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with a list of file paths concatenates all parametrized data"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    all_expected = ["line0", "line1", "line2", "item0", "item1", "item2"]
    assert data == all_expected[idx]


# Binary files
@parametrize("data", PATH_JPEG_FILE, parametrizer=lambda d: _split_jpeg(d))  # noqa: PLW0108
def test_parametrize_binary_file_with_parametrizer(request: FixtureRequest, data: bytes) -> None:
    """Test @parametrize loader with the parametrizer using binary file"""
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
    parametrizer=lambda d: [d],  # single param
    ids=lambda d: repr(d[:5]),
)
def test_parametrize_binary_file_with_ids(request: FixtureRequest, data: bytes) -> None:
    """Test @parametrize loader with the ids using binary file"""
    assert data == (ABS_PATH_LOADER_DIR / PATH_JPEG_FILE).read_bytes()
    # Pytest internally applies repr() for the ID, which double escapes the ID value the plugin specifies for bytes.
    # For testing purpose, we adjust the nodeid value pytest holds to match with what we specified
    assert request.node.nodeid.encode("utf-8").decode("unicode_escape").endswith(f"[{data[:5]!r}]")


@parametrize(
    "data",
    PATH_JPEG_FILE,
    parametrizer=lambda d: [d],  # single param
    marks=pytest.mark.foo,
)
def test_parametrize_binary_file_with_marks(request: FixtureRequest, data: bytes) -> None:
    """Test @parametrize loader with the marks using binary file"""
    assert request.node.get_closest_marker("foo")


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
