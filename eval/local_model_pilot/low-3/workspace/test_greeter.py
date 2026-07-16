import typing
from greeter import greet_user


def test_greet_valid_user():
    assert greet_user("Alice") == "Hello, Alice!"
    assert greet_user("  Bob  ") == "Hello, Bob!"


def test_greet_none():
    assert greet_user(None) == "Hello, Guest!"


def test_greet_empty_or_whitespace():
    assert greet_user("") == "Hello, Guest!"
    assert greet_user("   ") == "Hello, Guest!"


def test_type_annotations():
    annotations = typing.get_type_hints(greet_user)
    assert "username" in annotations
    assert "return" in annotations
