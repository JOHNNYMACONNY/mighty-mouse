_cached_val = None

def set_cache(val):
    global _cached_val
    _cached_val = val

def get_cached_value():
    return _cached_val
