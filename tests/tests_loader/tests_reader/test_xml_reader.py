import xml.etree.ElementTree as ET

import pytest

from pytest_data_loader import load, parametrize, parametrize_dir
from tests.tests_loader.helper import PATH_XML_FILE, PATH_XML_FILE_DIR

pytestmark = pytest.mark.readers


@load("tree", PATH_XML_FILE, file_reader=ET.parse)
def test_load_xml_file_with_reader(tree: ET.ElementTree) -> None:
    """Test @load loader with XML reader"""
    assert isinstance(tree, ET.ElementTree)
    root = tree.getroot()
    assert root is not None
    assert len(root) > 0
    for child in root:
        assert isinstance(child, ET.Element)
        assert child.tag == "child"


@load("root", PATH_XML_FILE, file_reader=ET.parse, onload_func=lambda tree: tree.getroot())
def test_load_xml_file_with_reader_and_onload_func(root: ET.Element) -> None:
    """Test @load loader with XML file reader and onload_func"""
    assert isinstance(root, ET.Element)
    assert root.tag == "root"
    assert len(root) > 0
    for child in root:
        assert isinstance(child, ET.Element)
        assert child.tag == "child"


@parametrize("elem", PATH_XML_FILE, file_reader=ET.parse, onload_func=lambda tree: tree.getroot())
def test_parametrize_xml_file_with_reader(elem: ET.Element) -> None:
    """Test @parametrize loader with XML file reader and onload_func"""
    assert isinstance(elem, ET.Element)
    assert elem.tag == "child"


@parametrize_dir(
    "root", PATH_XML_FILE_DIR, file_reader_func=lambda f: ET.parse, process_func=lambda tree: tree.getroot()
)
def test_parametrize_dir_with_xml_reader(root: ET.Element) -> None:
    """Test @parametrize_dir loader with XML file reader and process_func"""
    assert isinstance(root, ET.Element)
    assert len(root) > 0
    for child in root:
        assert isinstance(child, ET.Element)
        assert child.tag == "child"
