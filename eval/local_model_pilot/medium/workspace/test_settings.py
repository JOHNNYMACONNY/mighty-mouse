import pytest

from config_loader import Settings, load_settings
from service import request_timeout


def test_default_is_preserved():
    assert load_settings({}) == Settings(timeout_seconds=30)


def test_valid_override_reaches_service():
    assert request_timeout({"APP_TIMEOUT": "45"}) == 45


@pytest.mark.parametrize("value", ["1", "300"])
def test_boundary_values_are_valid(value):
    assert load_settings({"APP_TIMEOUT": value}).timeout_seconds == int(value)


@pytest.mark.parametrize("value", ["", "abc", "1.5", "0", "-1", "301"])
def test_invalid_values_are_actionable(value):
    with pytest.raises(ValueError, match="APP_TIMEOUT"):
        load_settings({"APP_TIMEOUT": value})
