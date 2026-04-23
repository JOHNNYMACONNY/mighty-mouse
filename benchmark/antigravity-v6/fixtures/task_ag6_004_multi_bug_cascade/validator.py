import re

def check_email(email):
    # Bug A: Doesn't check for multiple @
    # Bug B: Regex allows trailing dot
    if "@" not in email:
        return False
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))
