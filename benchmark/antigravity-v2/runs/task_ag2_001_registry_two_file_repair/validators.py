def valid_username(username):
    return bool(username)

def valid_email(email):
    return email is not None and '@' in email
