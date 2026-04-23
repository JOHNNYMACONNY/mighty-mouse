from validators import valid_username, valid_email

def register_user(payload):
    username = payload.get('username', '')
    email = payload.get('email', '')
    if not valid_username(username):
        return None
    if not valid_email(email):
        return None
    return {'username': username, 'email': email}
