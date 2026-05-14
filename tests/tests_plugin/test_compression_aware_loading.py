import gzip
from pathlib import Path

import pytest
from pytest import ExitCode, Pytester

from pytest_data_loader.constants import DEFAULT_LOADER_DIR_NAME
from pytest_data_loader.paths import SUPPORTED_COMPRESSION_EXTENSIONS, compression_aware_open

pytestmark = pytest.mark.plugin


class TestCompressionAwareLoading:
    """Tests for compression aware loading"""

    @pytest.fixture(autouse=True)
    def data_dir(self, pytester: Pytester) -> Path:
        return pytester.mkdir(DEFAULT_LOADER_DIR_NAME)

    @pytest.mark.parametrize("ext", SUPPORTED_COMPRESSION_EXTENSIONS)
    def test_load_compressed_file(self, pytester: Pytester, data_dir: Path, ext: str) -> None:
        """Test that @load with a compressed file returns the decompressed content"""
        text_payload = "line1\nline2\n"
        compressed_path = data_dir / f"text.txt{ext}"
        with compression_aware_open(compressed_path, mode="wt", encoding="utf-8") as f:
            f.write(text_payload)

        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.load("data", {str(compressed_path)!r})
        def test_func(data):
            assert isinstance(data, str)
            assert data.splitlines() == {text_payload.splitlines()!r}
        """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_parametrize_compressed_file(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that @parametrize with a compressed file returns the parametrized decompressed content"""
        lines = ["alpha", "beta", "gamma"]
        gz_path = data_dir / "test.txt.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write("\n".join(lines))

        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.parametrize("data", {str(gz_path)!r})
        def test_func(data):
            assert data in {lines!r}
        """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=len(lines))

    def test_parametrize_dir_compressed_files(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that @parametrize_dir with a compressed files returns the decompressed file content"""
        sub_dir = data_dir / "dir"
        sub_dir.mkdir()
        for ext in SUPPORTED_COMPRESSION_EXTENSIONS:
            path = sub_dir / f"test.txt{ext}"
            with compression_aware_open(path, mode="wt", encoding="utf-8") as f:
                f.write("test\n")

        pytester.makepyfile(f"""
        import pytest_data_loader

        @pytest_data_loader.parametrize_dir("data", {sub_dir.name!r})
        def test_func(data):
            assert data == "test"
        """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=len(SUPPORTED_COMPRESSION_EXTENSIONS))

    def test_load_compressed_file_with_reader(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that a specified reader is effective to a compressed file"""
        payload = "key1: value1\nkey2: value2\n"
        gz_path = data_dir / "data.yml.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write(payload)

        pytester.makepyfile(f"""
        import yaml
        import pytest_data_loader

        @pytest_data_loader.load("data", {str(gz_path.name)!r}, reader=yaml.safe_load)
        def test_func(data):
            assert data == yaml.safe_load({payload!r})
        """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)

    def test_compressed_file_with_registered_reader(self, pytester: Pytester, data_dir: Path) -> None:
        """Test that a registered reader is effective to a compressed file"""
        payload = "key1: value1\nkey2: value2\n"
        gz_path = data_dir / "data.yml.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write(payload)

        pytester.makeconftest("""
        import yaml
        import pytest_data_loader

        pytest_data_loader.register_reader(".yml", yaml.safe_load)
        """)

        pytester.makepyfile(f"""
        import yaml
        import pytest_data_loader

        @pytest_data_loader.load("data", {str(gz_path.name)!r})
        def test_func(data):
            assert data == yaml.safe_load({payload!r})
        """)

        result = pytester.runpytest("-v")
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=1)
