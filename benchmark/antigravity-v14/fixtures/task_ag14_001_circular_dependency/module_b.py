# module_b.py
from base import get_a_value

def display_all():
    # Uses value from A
    return f"B + {get_a_value()}"
