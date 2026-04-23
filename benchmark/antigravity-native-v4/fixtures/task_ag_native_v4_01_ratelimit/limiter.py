class SlidingWindowRateLimiter:
    def __init__(self, window_size, max_requests):
        self.window_size = window_size
        self.max_requests = max_requests
        self.user_requests = {} # user_id -> list of timestamps

    def is_allowed(self, user_id, timestamp):
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # 1. Filter out timestamps older than the window
        expiry_limit = timestamp - self.window_size
        self.user_requests[user_id] = [t for t in self.user_requests[user_id] if t > expiry_limit]
        
        # 2. Check capacity
        if len(self.user_requests[user_id]) < self.max_requests:
            self.user_requests[user_id].append(timestamp)
            return True
        
        return False
