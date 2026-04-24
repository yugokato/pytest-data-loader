from pytest import FixtureRequest


def get_parametrized_test_idx(request: FixtureRequest, arg_name: str) -> int:
    return request.node.callspec.indices[arg_name]
