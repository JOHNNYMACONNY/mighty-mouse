import os
import shutil

class CacheGuard:
    def __init__(self, path):
        self.path = path
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.path):
            # Preserving recursive cleanup depth using shutil.rmtree
            shutil.rmtree(self.path)

def clear_cache(path):
    # Legacy wrapper for backward compatibility
    with CacheGuard(path):
        pass
