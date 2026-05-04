import sys
import importlib.util

class RedirectFinder:
    # Custom import finder to redirect legacy API calls to modern implementations
    def find_spec(self, fullname, path, target=None):
        if fullname == "legacy_api":
            # Finding the spec for the modern replacement
            return importlib.util.find_spec("modern_api")
        return None

def register_redirect():
    # Injecting the redirect finder into the front of the meta path
    # This ensures that legacy API requests are intercepted before standard finders run
    sys.meta_path.insert(0, RedirectFinder())
