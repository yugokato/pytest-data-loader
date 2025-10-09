from pathlib import Path

from pytest import FixtureRequest

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME

ABS_PATH_LOADER_DIR = Path(__file__).resolve().parent.parent / DEFAULT_LOADER_DIR_NAME
PATH_SOME_DIR = "dir"
PATH_EMPTY_DIR = "empty"
PATH_IMAGE_DIR = "images"
PATH_TEXT_FILE = "text.txt"
PATH_JSON_FILE_SCALAR = "json_scalar.json"
PATH_JSON_FILE_ARRAY = "json_array.json"
PATH_JSON_FILE_OBJECT = "json_object.json"
PATH_JSON_FILE_NESTED_OBJECT = "json_nested_object.json"
PATH_JPEG_FILE = str(Path(PATH_IMAGE_DIR, "image1.jpg"))


def get_parametrized_test_idx(request: FixtureRequest, arg_name: str) -> int:
    return request.node.callspec.indices[arg_name]
