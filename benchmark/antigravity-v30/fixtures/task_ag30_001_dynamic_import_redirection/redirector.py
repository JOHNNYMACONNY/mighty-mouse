import sys
import importlib.util

class DynamicRedirector:
    def __init__(self):
        self.mappings = {}
    def add_mapping(self, old, new):
        self.mappings[old] = new
    def find_spec(self, fullname, path, target=None):
        return None

_INSTANCE = None
def get_redirector():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DynamicRedirector()
        sys.meta_path.insert(0, _INSTANCE)
    return _INSTANCE
