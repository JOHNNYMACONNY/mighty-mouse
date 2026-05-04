import functools
def memoize(func):
    @functools.wraps(func)
    def wrapper(self, *args):
        if not hasattr(self, '_memo_cache'): self._memo_cache = {}
        if args not in self._memo_cache: self._memo_cache[args] = func(self, *args)
        return self._memo_cache[args]
    return wrapper