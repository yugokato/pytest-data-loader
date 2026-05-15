from collections.abc import Sequence

import pytest
from pypdf import PageObject, PdfReader
from pytest import FixtureRequest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.paths import PATH_PDF_FILE, PATH_PDF_FILE_DIR

from ..helper import get_parametrized_test_idx

pytestmark = pytest.mark.readers


@load("data", PATH_PDF_FILE, reader=PdfReader, read_options={"mode": "rb"})
def test_load_pdf_file_with_reader(data: PdfReader) -> None:
    """Test @load loader with PDF file reader"""
    assert isinstance(data, PdfReader)


@load("data", PATH_PDF_FILE, reader=PdfReader, read_options={"mode": "rb"}, onload=lambda r: r.pages)
def test_load_pdf_file_with_reader_with_onload(data: Sequence[PageObject]) -> None:
    """Test @load loader with PDF file reader and onload"""
    assert isinstance(data, Sequence)
    assert all(isinstance(x, PageObject) for x in data)


@parametrize(
    "data",
    PATH_PDF_FILE,
    reader=PdfReader,
    read_options={"mode": "rb"},
    parametrizer=lambda r: r.pages,
    processor=lambda p: p.extract_text().rstrip(),
)
def test_parametrize_pdf_file_with_reader(request: FixtureRequest, data: str) -> None:
    """Test @parametrize loader with PDF file reader and loader functions"""
    assert isinstance(data, str)
    idx = get_parametrized_test_idx(request, "data")
    assert data == f"Page{idx + 1}"


@parametrize_dir("data", PATH_PDF_FILE_DIR, read_options={"mode": "rb"}, reader=lambda f: PdfReader)
def test_parametrize_dir_with_pdf_reader(data: PdfReader) -> None:
    """Test @parametrize_dr loader with PDF file reader"""
    assert isinstance(data, PdfReader)
