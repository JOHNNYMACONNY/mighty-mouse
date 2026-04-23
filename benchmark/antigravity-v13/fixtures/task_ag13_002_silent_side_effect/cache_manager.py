from memoize import get_cached_config

def verify_cache_state():
    # Relies on the exact internal dict being accessible via __defaults__
    cache_dict = get_cached_config.__defaults__[0]
    return len(cache_dict)
