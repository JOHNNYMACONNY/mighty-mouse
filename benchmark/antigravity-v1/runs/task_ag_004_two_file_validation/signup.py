from validators import validate_email, validate_name

def validate_signup(payload):
    email = payload.get('email', '')
    name = payload.get('name', '')
    return validate_email(email) and validate_name(name)
