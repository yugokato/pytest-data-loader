from __future__ import annotations

import sys
from enum import Enum
from typing import Any

if sys.version_info < (3, 11):
    from typing_extensions import Unpack

    class StrEnum(str, Enum):
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:  # type: ignore[override]
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum  # noqa: F401
    from typing import Unpack  # noqa: F401
