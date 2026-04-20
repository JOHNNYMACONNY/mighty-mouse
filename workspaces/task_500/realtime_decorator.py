from functools import wraps
import time

class CircuitBreakerOpenException(Exception):
    pass

def realtime_circuit_breaker(failure_threshold=3, reset_timeout=60):
    """
    Decorator following the Circuit Breaker pattern.
    Closed: Everything is normal.
    Open: Threshold reached, calls blocked for reset_timeout.
    Half-Open: After timeout, allows one call to test health.
    """
    def decorator(func):
        # State stored in decorator closure
        state = {
            'status': 'CLOSED',
            'failures': 0,
            'last_failure_time': 0
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # 1. State Transition: Open -> Half-Open (Temporal)
            if state['status'] == 'OPEN':
                if now - state['last_failure_time'] > reset_timeout:
                    state['status'] = 'HALF_OPEN'
                    print("[CircuitBreaker] Transitioned to HALF_OPEN")
                else:
                    raise CircuitBreakerOpenException("Circuit is OPEN, calls blocked.")

            # 2. Execution
            try:
                result = func(*args, **kwargs)
                
                # 3. Success Handling
                if state['status'] == 'HALF_OPEN':
                    state['status'] = 'CLOSED'
                    state['failures'] = 0
                    print("[CircuitBreaker] Circuit RESET (CLOSED)")
                
                return result
                
            except Exception as e:
                state['failures'] += 1
                state['last_failure_time'] = time.time()
                
                # 4. State Transition: Closed -> Open
                if state['failures'] >= failure_threshold:
                    state['status'] = 'OPEN'
                    print(f"[CircuitBreaker] Threshold reached ({state['failures']}). Circuit OPENED.")
                
                raise e

        return wrapper
    return decorator
