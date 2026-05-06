# legacy_registry.py

import time
from typing import Dict, Any

class RateLimiter:
    """
    Implements a simple rate limiting mechanism using a fixed window counter.
    """
    def __init__(self):
        # Stores {key: {"count": int, "window_start": float}}
        self._state: Dict[Any, Dict[str, Any]] = {}

    def check_limit(self, key: Any, limit: int, period: float) -> bool:
        """
        Checks if the operation for the given key is within the defined rate limit.

        Args:
            key: The identifier for the resource being limited.
            limit: The maximum number of calls allowed.
            period: The time window in seconds.

        Returns:
            True if the operation is allowed, False otherwise.
        """
        current_time = time.time()

        if key not in self._state:
            # First time accessing this key
            self._state[key] = {"count": 1, "window_start": current_time}
            return True

        state = self._state[key]
        
        # Check if the current window has expired
        if current_time > state["window_start"] + period:
            # Window expired, reset counter and start new window
            self._state[key] = {"count": 1, "window_start": current_time}
            return True
        
        # Window is active, check count
        if state["count"] < limit:
            # Within limit, increment count
            self._state[key]["count"] += 1
            return True
        else:
            # Over limit
            return False

    def reset_state(self, key: Any):
        """Manually resets the state for a specific key."""
        if key in self._state:
            del self._state[key]

# Example usage (optional, for testing purposes)
if __name__ == '__main__':
    limiter = RateLimiter()
    key = "api_endpoint_A"
    limit = 3
    period = 2.0

    print(f"--- Testing Rate Limit ({limit} calls per {period} seconds) ---")
    
    # Test within limit
    for i in range(1, 5):
        allowed = limiter.check_limit(key, limit, period)
        print(f"Attempt {i}: {'ALLOWED' if allowed else 'BLOCKED'}")
        if not allowed:
            break
        time.sleep(0.1)

    print("\n--- Waiting 2.1 seconds to reset window ---")
    time.sleep(period + 0.1)

    # Test after reset
    allowed = limiter.check_limit(key, limit, period)
    print(f"Attempt after wait: {'ALLOWED' if allowed else 'BLOCKED'}")