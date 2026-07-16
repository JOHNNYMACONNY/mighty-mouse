import threading
import time
import pytest
from state_machine import ProcessStateMachine


def test_basic_transitions():
    sm = ProcessStateMachine()
    sm.transition_to("PENDING")
    assert sm.state == "PENDING"
    sm.transition_to("PROCESSING")
    assert sm.state == "PROCESSING"
    sm.transition_to("COMPLETED")
    assert sm.state == "COMPLETED"


def test_invalid_transition():
    sm = ProcessStateMachine()
    with pytest.raises(ValueError):
        sm.transition_to("PROCESSING")


def test_concurrent_transitions():
    sm = ProcessStateMachine()

    errors = []

    def run_a():
        try:
            sm.transition_to("PENDING")
        except Exception as e:
            errors.append(e)

    def run_b():
        try:
            time.sleep(0.002)  # Try to transition while A is in time.sleep
            sm.transition_to("PROCESSING")
        except Exception as e:
            errors.append(e)

    ta = threading.Thread(target=run_a)
    tb = threading.Thread(target=run_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    assert (
        not errors
    ), f"Errors occurred during concurrent transitions: {errors}"
    assert sm.state == "PROCESSING"
