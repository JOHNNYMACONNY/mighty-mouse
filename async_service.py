import asyncio
import time
from typing import Callable, Any, Awaitable

# --- Custom Exceptions for Reliability ---

class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and preventing service calls."""
    def __init__(self, retry_after: float):
        super().__init__(f"Circuit breaker is open. Service unavailable. Retry after {retry_after:.2f} seconds.")
        self.retry_after = retry_after

class ServiceFailureError(Exception):
    """Base exception for service-related failures that should trip the breaker."""
    pass

# --- Circuit Breaker Implementation ---

class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern for asynchronous service calls.
    Ensures that repeated failures prevent cascading failures by opening the circuit.
    """
    
    # States
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0, failure_exception: type = ServiceFailureError):
        """
        Initializes the circuit breaker state machine.
        :param failure_threshold: Number of consecutive failures required to trip the circuit.
        :param recovery_timeout: Time (seconds) the circuit remains open before transitioning to Half-Open.
        :param failure_exception: The specific exception type that counts as a failure.
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_exception = failure_exception
        
        # State variables
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def __call__(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """
        Wraps the asynchronous function call with circuit breaker logic.
        """
        async with self._lock:
            if self._state == self.OPEN:
                # Check if the timeout has passed
                time_since_failure = time.monotonic() - self._last_failure_time
                if time_since_failure > self._recovery_timeout:
                    print("Circuit Breaker: Timeout elapsed. Transitioning to HALF-OPEN.")
                    self._state = self.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError(self._recovery_timeout - time_since_failure)

        # Execute the function call (outside the lock to avoid deadlocks during long operations)
        try:
            result = await func(*args, **kwargs)
            
            # Success path: Reset state
            await self._reset_state()
            return result

        except self._failure_exception as e:
            # Failure path: Handle service-specific failures
            await self._record_failure()
            raise e
        except Exception as e:
            # Non-service failure: Do not trip the breaker, but log/handle defensively
            print(f"Warning: Non-service related exception caught: {type(e).__name__}. Breaker state unchanged.")
            raise e

    async def _record_failure(self):
        """Handles state transition upon failure."""
        async with self._lock:
            if self._state == self.HALF_OPEN:
                # Failure in Half-Open state immediately trips back to Open
                self._state = self.OPEN
                self._last_failure_time = time.monotonic()
                self._failure_count = 1
                print("Circuit Breaker: Failure in HALF-OPEN. Tripping back to OPEN.")
            elif self._state == self.CLOSED:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                print(f"Circuit Breaker: Failure recorded. Count: {self._failure_count}/{self._failure_threshold}.")
                
                if self._failure_count >= self._failure_threshold:
                    self._state = self.OPEN
                    print(f"Circuit Breaker: Threshold reached ({self._failure_threshold}). Transitioning to OPEN.")
            # If already OPEN, do nothing, just update time if necessary (though time check handles this)

    async def _reset_state(self):
        """Resets the state machine upon successful call."""
        async with self._lock:
            if self._state != self.CLOSED:
                print("Circuit Breaker: Success detected. Transitioning to CLOSED.")
            self._state = self.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

# --- Example Usage ---

# Initialize the breaker globally or pass it where needed
# Example: Breaker for a hypothetical external API call
api_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

async def external_api_call(data: str) -> str:
    """Simulates an external service call that might fail."""
    print(f"\n[Attempting API call with data: {data}]")
    # Simulate network latency
    await asyncio.sleep(0.1)
    
    # Simulate failure based on data content for testing
    if "fail" in data:
        raise ServiceFailureError(f"API failed processing '{data}'")
    
    return f"Successfully processed {data}"

async def run_service_call(data: str):
    """Wrapper function demonstrating the use of the circuit breaker."""
    try:
        # Use the breaker instance to wrap the function call
        result = await api_breaker(external_api_call, data)
        print(f"Service Call SUCCESS: {result}")
    except CircuitBreakerOpenError as e:
        print(f"Service Call BLOCKED: {e}")
    except ServiceFailureError as e:
        print(f"Service Call FAILED (Tripping Breaker): {e}")
    except Exception as e:
        print(f"Service Call CRITICAL FAILURE: {e}")

# Example usage (optional, for testing):
# async def main():
#     print("--- Test 1: Initial Success ---")
#     await awaitable_call(awaitable_call)
#     
#     print("\n--- Test 2: Triggering Failure (3 times) ---")
#     for i in range(1, 4):
#         await awaitable_call(f"Fail {i}")
#     
#     print("\n--- Test 3: Circuit Open (Should fail immediately) ---")
#     await awaitable_call("Fail 4")
#     
#     print("\n--- Test 4: Waiting for timeout (Simulated wait) ---")
#     # In a real scenario, we would wait for the timeout period.
#     # For this example, we just show the structure.
#     print("Circuit is open. Must wait for timeout period to attempt recovery.")
#     
# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())