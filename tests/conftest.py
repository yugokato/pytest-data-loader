from typing import Any


def pytest_make_parametrize_id(val: Any, argname: str) -> str:
    if callable(val):
        val = val.__name__
    return f"{argname}={val!r}"
