import os
import shutil

def clear_cache(path):
    if os.path.exists(path):
        shutil.rmtree(path)
