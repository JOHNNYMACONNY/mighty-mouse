import time
import functools

def retry_with_backoff(max_retries=3, base_delay=0.1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ValueError as e:
                    last_exc = e
                    time.sleep(delay)
                    delay *= 2
            raise last_exc
        return wrapper
    return decorator
