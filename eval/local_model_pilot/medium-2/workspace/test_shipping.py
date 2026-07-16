import ast
import inspect
from shipping import calculate_shipping


def test_shipping_costs():
    assert calculate_shipping("standard", 10.0) == 10.0
    assert calculate_shipping("express", 10.0) == 20.0
    assert calculate_shipping("overnight", 10.0) == 40.0
    assert calculate_shipping("saver", 10.0) == 8.0


def test_invalid_method():
    try:
        calculate_shipping("teleport", 10.0)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "Unknown shipping method" in str(e) or "teleport" in str(e)


def test_is_refactored():
    source = inspect.getsource(calculate_shipping)
    tree = ast.parse(source)
    if_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if_count += 1
    assert (
        if_count <= 2
    ), f"Refactored code should use dictionary dispatch and have at most 2 'if' conditions (got {if_count})"
