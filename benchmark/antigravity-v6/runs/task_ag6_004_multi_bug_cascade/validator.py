import re

def check_email(email):
    # Fixed: added @ count check and improved regex with end anchor
    if email.count("@") != 1:
        return False
    # Regex ensures no trailing dot and proper structure
    return bool(re.match(r"[^@]+@[^@]+\.[^@.]+$", email))
