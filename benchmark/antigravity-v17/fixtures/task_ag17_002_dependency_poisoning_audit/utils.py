_call_count = 0

def increment_and_get():
    global _call_count
    _call_count += 1
    return _call_count

def reset_counter():
    global _call_count
    _call_count = 0
