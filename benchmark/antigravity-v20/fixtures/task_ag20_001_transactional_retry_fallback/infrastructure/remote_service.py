_fail_count = 0
_max_fails = 0

def set_fail_config(max_fails):
    global _fail_count, _max_fails
    _fail_count = 0
    _max_fails = max_fails

def get_data():
    global _fail_count
    if _fail_count < _max_fails:
        _fail_count += 1
        raise Exception("SERVICE_UNAVAILABLE")
    return "FRESH_DATA"
