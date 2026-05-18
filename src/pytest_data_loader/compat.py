from __future__ import annotations

import sys
from enum import Enum
from typing import Any

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self  # noqa: F401

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        @staticmethod
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum  # noqa: F401
