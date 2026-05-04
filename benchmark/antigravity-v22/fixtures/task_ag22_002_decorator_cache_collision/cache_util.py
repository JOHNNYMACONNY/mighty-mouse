import functools

_INTERNAL_CACHE = {}

def memoize(func):
    @functools.wraps(func)
    def wrapper(self, *args):
        if args not in _INTERNAL_CACHE:
            _INTERNAL_CACHE[args] = func(self, *args)
        return _INTERNAL_CACHE[args]
    return wrapper
