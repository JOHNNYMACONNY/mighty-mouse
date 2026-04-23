from limiter import SlidingWindowRateLimiter

def test_rate_limiter():
    limiter = SlidingWindowRateLimiter(window_size=60, max_requests=2)
    
    # User 1: 2 requests allowed
    assert limiter.is_allowed("user1", 100) == True
    assert limiter.is_allowed("user1", 110) == True
    # User 1: 3rd request blocked
    assert limiter.is_allowed("user1", 120) == False
    
    # User 1: After 60 seconds, window slides
    assert limiter.is_allowed("user1", 161) == True # 100 falls out, 110 and 161 remain
    assert limiter.is_allowed("user1", 165) == False # 110 and 161 are in, 3rd blocked
    
    # User 2: Independent window
    assert limiter.is_allowed("user2", 100) == True
    
    print("PASS")

if __name__ == "__main__":
    test_rate_limiter()
