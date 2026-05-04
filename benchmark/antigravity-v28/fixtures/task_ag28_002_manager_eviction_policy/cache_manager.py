import multiprocessing

class LimitedSharedDict:
    def __init__(self, shared_dict, keys_order_list, lock, max_keys):
        self.data = shared_dict
        self.order = keys_order_list
        self.lock = lock
        self.max_keys = max_keys

    def set(self, key, value):
        self.data[key] = value
