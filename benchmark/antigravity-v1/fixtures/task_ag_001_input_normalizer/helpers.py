import re

def normalize_name(value):
    if value is None:
        return None
    return value.strip()
