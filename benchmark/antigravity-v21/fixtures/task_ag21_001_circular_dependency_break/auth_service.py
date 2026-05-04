import user_service

def is_logged_in(uid):
    return uid == "123"

def authenticate(uid, token):
    name = user_service.get_user_name(uid)
    return f"Authenticated {name}"
