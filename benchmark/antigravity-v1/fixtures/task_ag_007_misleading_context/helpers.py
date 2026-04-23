import re

def normalize_slug(value):
    if value is None:
        return ''
    return value.replace(' ', '-').lower()
