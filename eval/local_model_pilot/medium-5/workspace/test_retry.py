from unittest.mock import Mock, patch
import pytest
from retry_client import retry_call


def test_success_first_attempt():
    func = Mock(return_value="success")
    with patch("time.sleep") as mock_sleep:
        res, attempts = retry_call(func, (ValueError,))
        assert res == "success"
        assert attempts == 1
        mock_sleep.assert_not_called()


def test_success_after_retries():
    func = Mock(side_effect=[ValueError("fail 1"), ValueError("fail 2"), "success"])
    with patch("time.sleep") as mock_sleep:
        res, attempts = retry_call(
            func, (ValueError,), max_retries=3, initial_delay=0.1, backoff_factor=2
        )
        assert res == "success"
        assert attempts == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)


def test_max_retries_exceeded():
    func = Mock(side_effect=ValueError("always fail"))
    with patch("time.sleep") as mock_sleep:
        with pytest.raises(ValueError, match="always fail"):
            retry_call(
                func, (ValueError,), max_retries=3, initial_delay=0.1, backoff_factor=2
            )
        assert func.call_count == 4
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)
        mock_sleep.assert_any_call(0.4)


def test_unhandled_exception():
    func = Mock(side_effect=KeyError("unhandled"))
    with patch("time.sleep") as mock_sleep:
        with pytest.raises(KeyError):
            retry_call(func, (ValueError,))
        assert func.call_count == 1
        mock_sleep.assert_not_called()
