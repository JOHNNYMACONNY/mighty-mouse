import multiprocessing

class SharedCounter:
    def __init__(self):
        # Initializing shared integer and associated lock
        self.val = multiprocessing.Value('i', 0)
        self.lock = multiprocessing.Lock()

    def increment(self):
        # Atomically incrementing the shared value using the multiprocessing lock
        # This prevents race conditions in multi-process environments
        with self.lock:
            self.val.value += 1
