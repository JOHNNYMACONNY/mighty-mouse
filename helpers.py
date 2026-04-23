import re

def normalize_name(value):
    """
    Normalizes a string by trimming leading/trailing whitespace,
    collapsing internal whitespace runs to a single space,
    returning an empty string for None, and preserving punctuation.
    """
    if value is None:
        return ""
    return " ".join(value.split())

def safe_divide(a, b):
    """
    Performs division but returns None if the divisor is zero.
    """
    if b == 0:
        return None
    return a / b

def is_enabled(value):
    """
    Checks if a value represents a truthy environment flag.
    Truthy: '1', 'true', 'yes', 'on'
    Falsy: '0', 'false', 'no', 'off', ''
    """
    return str(value).lower() in ('1', 'true', 'yes', 'on')

def currency_symbol():
    """
    Returns the currency symbol.
    """
    return "$"

def format_price(value):
    """
    Formats a numeric value as a price string with two decimal places.
    Returns "0.00" for None.
    """
    if value is None:
        return f"{currency_symbol()}0.00"
    return f"{currency_symbol()}{float(value):,.2f}"

def normalize_slug(value):
    """
    Normalizes a string for use in a URL slug.
    - lower-case input
    - replace spaces with hyphens
    - collapse repeated hyphens
    - trim hyphens from both ends
    """
    if value is None:
        return ""
    # Lower-case
    s = value.lower()
    # Replace spaces with hyphens
    s = s.replace(" ", "-")
    # Collapse repeated hyphens
    s = re.sub(r"-+", "-", s)
    # Trim hyphens
    return s.strip("-")

def smart_sort(items):
    """
    Sorts a list of items.
    
    AMBIGUITY: The desired case-sensitivity was not specified in the bug report.
    ASSUMPTION: We assume case-insensitive sorting (e.g., 'A' and 'a' together) 
    is more intuitive for users, but we use the original value as a tie-breaker 
    to ensure a stable and deterministic order.
    """
    if items is None:
        return []

    def _safe_key(x):
        # We use a type-prefix to ensure consistent grouping and avoid TypeErrors
        # when comparing incompatible types (like int and str).
        if isinstance(x, (int, float)):
            return (0, x, "")
        if isinstance(x, str):
            return (1, x.lower(), x)
        return (2, str(x).lower(), str(x))

    return sorted(items, key=_safe_key)
