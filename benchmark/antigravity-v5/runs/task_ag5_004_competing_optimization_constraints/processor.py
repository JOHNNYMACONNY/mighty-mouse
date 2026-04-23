import time
from concurrent.futures import ThreadPoolExecutor

def _process_item(item):
    time.sleep(0.01)
    return item * 2

def apply_filter(data):
    # Parallelized using ThreadPoolExecutor as per LIMITS.md constraints (no multiprocessing)
    with ThreadPoolExecutor() as executor:
        return list(executor.map(_process_item, data))
