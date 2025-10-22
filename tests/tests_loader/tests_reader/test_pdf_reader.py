from collections.abc import Sequence

import pytest
from pypdf import PageObject, PdfReader
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import PATH_PDF_FILE, PATH_PDF_FILE_DIR, get_parametrized_test_idx

pytestmark = pytest.mark.readers


@load("data", PATH_PDF_FILE, file_reader=PdfReader, mode="rb")
def test_load_pdf_file_with_reader(data: PdfReader) -> None:
    """Test @load loader with PDF file reader"""
    assert isinstance(data, PdfReader)


@load("data", PATH_PDF_FILE, file_reader=PdfReader, onload_func=lambda r: r.pages, mode="rb")
def test_load_pdf_file_with_reader_with_onload_func(data: Sequence[PageObject]) -> None:
    """Test @load loader with PDF file reader and onload_func"""
    assert isinstance(data, Sequence)
    assert all(isinstance(x, PageObject) for x in data)


@parametrize(
    "data",
    PATH_PDF_FILE,
    file_reader=PdfReader,
    parametrizer_func=lambda r: r.pages,
    process_func=lambda p: p.extract_text().rstrip(),
    mode="rb",
)
def test_parametrize_pdf_file_with_reader(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with PDF file reader and loader functions"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"Page{idx + 1}"


@parametrize_dir(
    "data", PATH_PDF_FILE_DIR, file_reader_func=lambda f: PdfReader, read_option_func=lambda f: {"mode": "rb"}
)
def test_parametrize_dir_with_pdf_reader(data: PdfReader) -> None:
    """Test @parametrize_dr loader with PDF file reader"""
    assert isinstance(data, PdfReader)
