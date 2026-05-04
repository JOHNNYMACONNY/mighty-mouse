import multiprocessing

class LimitedSharedDict:
    def __init__(self, shared_dict, keys_order_list, lock, max_keys):
        # Initializing shared state components
        self.data = shared_dict      # Managed Dict
        self.order = keys_order_list  # Managed List (FIFO tracker)
        self.lock = lock             # Managed Lock
        self.max_keys = max_keys

    def set(self, key, value):
        # Ensuring atomic access to the shared data structure
        with self.lock:
            if key not in self.data:
                # Eviction logic: Remove oldest entry if limit reached
                while len(self.data) >= self.max_keys:
                    if self.order:
                        oldest_key = self.order.pop(0)
                        if oldest_key in self.data:
                            del self.data[oldest_key]
                    else:
                        # Fallback if order list is somehow desynced
                        break
                
                # Registering the new key in the order list
                self.order.append(key)
            
            # Storing/Updating the actual data
            self.data[key] = value
