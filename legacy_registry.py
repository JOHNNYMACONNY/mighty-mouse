import time
import threading
from typing import Callable, Any, Dict

class RateLimiter:
    """
    Implements a thread-safe rate limiter using a sliding window counter approach.
    """
    def __init__(self, max_requests: int, window_size: float):
        """
        Initializes the rate limiter.
        :param max_requests: The maximum number of requests allowed.
        :param window_size: The time window in seconds.
        """
        if max_requests <= 0 or window_size <= 0:
            raise ValueError("Max requests and window size must be positive.")
            
        self.max_requests = max_requests
        self.window_size = window_size
        # State: {key: {'count': int, 'timestamp': float}}
        self._state: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def check_limit(self, key: str) -> bool:
        """
        Checks if the given key is within the rate limit.
        Returns True if allowed, False otherwise.
        """
        current_time = time.time()
        
        with self._lock:
            state = self._state.get(key)
            
            if state is None:
                # First request for this key
                self._state[key] = {'count': 1, 'timestamp': current_time}
                return True
            
            # Check if the window has expired
            elapsed_time = current_time - state['timestamp']
            if elapsed_time > self.window_size:
                # Window expired, reset counter
                self._state[key] = {'count': 1, 'timestamp': current_time}
                return True
            
            # Window active, check count
            if state['count'] < self.max_requests:
                self._state[key]['count'] += 1
                return True
            else:
                # Limit exceeded
                return False

    def execute_with_limit(self, key: str, action: Callable[[], Any]) -> Any:
        """
        Executes the given action only if the rate limit allows it.
        Raises RateLimitExceeded if the limit is hit.
        """
        if not self.check_limit(key):
            raise RateLimitExceeded(
                f"Rate limit exceeded for key '{key}'. Try again after {self.window_size} seconds."
            )
        
        # Execute the protected action
        return action()

class RateLimitExceeded(Exception):
    """Custom exception raised when the rate limit is exceeded."""
    pass

def get_legacy_registry_rate_limiter(max_requests: int, window_size: float) -> RateLimiter:
    """
    Factory function to provide the initialized rate limiter instance.
    """
    return RateLimiter(max_requests, window_size)