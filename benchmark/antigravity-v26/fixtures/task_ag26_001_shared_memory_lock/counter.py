import multiprocessing

class SharedCounter:
    def __init__(self):
        self.val = multiprocessing.Value("i", 0)
        self.lock = multiprocessing.Lock()

    def increment(self):
        self.val.value += 1
