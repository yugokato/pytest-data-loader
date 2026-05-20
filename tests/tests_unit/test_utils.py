import pytest

from pytest_data_loader.utils import to_bytes

pytestmark = pytest.mark.unittest


class TestToBytes:
    """Tests for the to_bytes() size-string parser."""

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("0MB", 0),
            ("1B", 1),
            ("1KB", 1_000),
            ("1MB", 1_000**2),
            ("1GB", 1_000**3),
            ("1TB", 1_000**4),
            ("1PB", 1_000**5),
        ],
    )
    def test_to_bytes_decimal_units(self, size: str, expected: int) -> None:
        """Test that decimal unit strings are converted correctly."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("0MiB", 0),
            ("1KiB", 1_024),
            ("1MiB", 1_024**2),
            ("1GiB", 1_024**3),
            ("1TiB", 1_024**4),
            ("1PiB", 1_024**5),
        ],
    )
    def test_to_bytes_binary_units(self, size: str, expected: int) -> None:
        """Test that binary unit strings are converted correctly."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("128MiB", 134_217_728),
            ("256MiB", 268_435_456),
        ],
    )
    def test_to_bytes_known_defaults(self, size: str, expected: int) -> None:
        """Test that the known plugin default values convert to the expected byte counts."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("0", 0),
            ("1048576", 1_048_576),
            ("134217728", 134_217_728),
        ],
    )
    def test_to_bytes_bare_integer(self, size: str, expected: int) -> None:
        """Test that bare integers (no unit) are treated as bytes."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("1mib", 1_024**2),
            ("1MIB", 1_024**2),
            ("1Mib", 1_024**2),
            ("1kb", 1_000),
            ("1KB", 1_000),
        ],
    )
    def test_to_bytes_case_insensitive(self, size: str, expected: int) -> None:
        """Test that unit parsing is case-insensitive."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            (" 1MiB", 1_024**2),
            ("1MiB ", 1_024**2),
            (" 1MiB ", 1_024**2),
            ("1 MiB", 1_024**2),
            ("1  MiB", 1_024**2),
        ],
    )
    def test_to_bytes_whitespace_tolerant(self, size: str, expected: int) -> None:
        """Test that surrounding and internal whitespace between value and unit is tolerated."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "size, expected",
        [
            ("1.5KiB", 1_536),
            ("0.5GB", 500_000_000),
            ("2.5MB", 2_500_000),
        ],
    )
    def test_to_bytes_fractional_with_unit(self, size: str, expected: int) -> None:
        """Test that fractional values are accepted when a unit is present."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize("size, expected", [(100, 100), (1024, 1024), (0, 0), (1.5, 1), (0.9, 0)])
    def test_to_bytes_passthrough_int_float(self, size: int | float, expected: int) -> None:
        """Test that int/float inputs are passed through directly as bytes."""
        assert to_bytes(size) == expected

    @pytest.mark.parametrize(
        "invalid",
        [
            "",
            " ",
            "-1",
            "abc",
            "1.5",
            "1e6",
            "1IB",
            "1.2.3MiB",
            "MiB",
            ".",
            "1.MiB",
        ],
    )
    def test_to_bytes_invalid_inputs_raise(self, invalid: str) -> None:
        """Test that invalid size strings raise ValueError with a descriptive message."""
        with pytest.raises(ValueError, match=f"Invalid value: {invalid.strip()!r}"):
            to_bytes(invalid)
