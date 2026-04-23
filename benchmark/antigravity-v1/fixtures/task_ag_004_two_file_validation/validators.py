def validate_email(email):
    return email is not None and '@' in email

def validate_name(name):
    return bool(name)
