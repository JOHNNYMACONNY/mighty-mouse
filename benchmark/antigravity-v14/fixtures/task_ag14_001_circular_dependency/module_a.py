# module_a.py
from base import get_b_value

def calculate_total():
    # Uses value from B
    return f"A + {get_b_value()}"
