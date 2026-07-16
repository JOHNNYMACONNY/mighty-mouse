import time
import threading


class TTLCache:

    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key):
        # Bug: Not thread-safe! The check and retrieve operations are not locked.
        if key not in self._cache:
            return None
        val, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        return val

    def set(self, key, value):
        with self._lock:
            self._cache[key] = (value, time.time() + self.ttl)
