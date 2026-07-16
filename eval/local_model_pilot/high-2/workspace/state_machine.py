import threading
import time


class ProcessStateMachine:
    ALLOWED_TRANSITIONS = {
        "INIT": {"PENDING"},
        "PENDING": {"PROCESSING", "FAILED"},
        "PROCESSING": {"COMPLETED", "FAILED"},
        "COMPLETED": set(),
        "FAILED": set(),
    }

    def __init__(self):
        self.state = "INIT"
        self._lock = threading.RLock()

    def transition_to(self, target_state: str):
        # Bug: Not acquiring self._lock during the check and write.
        current = self.state
        if target_state not in self.ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition from {current} to {target_state}")
        time.sleep(0.005)
        self.state = target_state
