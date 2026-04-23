from auth import authenticate
import time

def test_auth_failure_is_fast():
    # The test expects failed logins to be instantaneous (bad security practice!)
    start = time.time()
    authenticate("admin", "wrong")
    duration = time.time() - start
    assert duration < 0.1, "Failed login took too long, expected < 0.1s"
