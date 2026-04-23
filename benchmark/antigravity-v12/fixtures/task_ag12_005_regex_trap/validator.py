import re

# This regex is intentionally complex and slow on certain inputs
EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

def validate_email(email):
    return bool(re.match(EMAIL_REGEX, email))
