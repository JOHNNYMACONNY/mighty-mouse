import time
import threading
from cache import TTLCache


def test_basic_get_set():
    cache = TTLCache(ttl_seconds=1.0)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert cache.get("b") is None


def test_expiry():
    cache = TTLCache(ttl_seconds=0.1)
    cache.set("a", 1)
    time.sleep(0.2)
    assert cache.get("a") is None


def test_thread_safety():
    cache = TTLCache(ttl_seconds=0.5)

    errors = []

    def worker_write(i):
        try:
            for j in range(100):
                cache.set(f"key_{j}", i)
        except Exception as e:
            errors.append(e)

    def worker_read():
        try:
            for j in range(100):
                cache.get(f"key_{j}")
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(10):
        t_w = threading.Thread(target=worker_write, args=(i,))
        t_r = threading.Thread(target=worker_read)
        threads.extend([t_w, t_r])
        t_w.start()
        t_r.start()

    for t in threads:
        t.join()

    assert not errors, f"Encountered thread-safety errors: {errors}"
