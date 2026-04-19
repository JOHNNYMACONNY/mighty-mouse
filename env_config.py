import os

def get_config(key, default=None):
    return os.environ.get(key, default)
