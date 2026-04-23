def get_cached_config(key, _cache={}):
    if key not in _cache:
        # Simulate expensive operation
        _cache[key] = f"config_for_{key}"
    return _cache[key]
