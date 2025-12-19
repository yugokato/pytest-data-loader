from pathlib import Path

from pytest import FixtureRequest

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME

ABS_PATH_LOADER_DIR = Path(__file__).resolve().parent.parent / DEFAULT_LOADER_DIR_NAME
PATH_SOME_DIR = "dir"
PATH_SOME_DIR_INNER = "dir_inner"
PATH_FILES_DIR = "files"
PATH_EMPTY_DIR = "empty"
PATH_IMAGE_DIR = "images"
PATH_JSON_FILE_DIR = Path(PATH_FILES_DIR, "json")
PATH_CSV_FILE_DIR = Path(PATH_FILES_DIR, "csv")
PATH_XML_FILE_DIR = Path(PATH_FILES_DIR, "xml")
PATH_YAML_FILE_DIR = Path(PATH_FILES_DIR, "yaml")
PATH_TOML_FILE_DIR = Path(PATH_FILES_DIR, "toml")
PATH_INI_FILE_DIR = Path(PATH_FILES_DIR, "ini")
PATH_PDF_FILE_DIR = Path(PATH_FILES_DIR, "pdf")

PATH_TEXT_FILE = Path(PATH_FILES_DIR, "text.txt")
PATH_JSON_FILE_SCALAR = PATH_JSON_FILE_DIR / "scalar.json"
PATH_JSON_FILE_ARRAY = PATH_JSON_FILE_DIR / "array.json"
PATH_JSON_FILE_OBJECT = PATH_JSON_FILE_DIR / "object.json"
PATH_JSON_FILE_NESTED_OBJECT = PATH_JSON_FILE_DIR / "object_nested.json"
PATH_CSV_FILE = PATH_CSV_FILE_DIR / "comma.csv"
PATH_CSV_FILE_SEMICOLON = PATH_CSV_FILE_DIR / "semicolon.csv"
PATH_XML_FILE = PATH_XML_FILE_DIR / "xml1.0.xml"
PATH_YAML_FILE = PATH_YAML_FILE_DIR / "yaml.yml"
PATH_YAML_DOCUMENTS_FILE = PATH_YAML_FILE_DIR / "yaml_documents.yml"
PATH_TOML_FILE = PATH_TOML_FILE_DIR / "toml.toml"
PATH_INI_FILE = PATH_INI_FILE_DIR / "ini.ini"
PATH_PDF_FILE = PATH_PDF_FILE_DIR / "pdf.pdf"
PATH_JPEG_FILE = Path(PATH_IMAGE_DIR, "image.jpg")

PATHS_TEXT_FILES = [
    PATH_TEXT_FILE,
    PATH_JSON_FILE_SCALAR,
    PATH_JSON_FILE_ARRAY,
    PATH_JSON_FILE_OBJECT,
    PATH_JSON_FILE_NESTED_OBJECT,
    PATH_CSV_FILE,
    PATH_CSV_FILE_SEMICOLON,
    PATH_XML_FILE,
    PATH_YAML_FILE,
    PATH_YAML_DOCUMENTS_FILE,
    PATH_TOML_FILE,
    PATH_INI_FILE,
]
PATHS_BINARY_FILES = [PATH_PDF_FILE, PATH_JPEG_FILE]


def get_parametrized_test_idx(request: FixtureRequest, arg_name: str) -> int:
    return request.node.callspec.indices[arg_name]
