import auth_service

def get_user_name(uid):
    if auth_service.is_logged_in(uid):
        return f"User_{uid}"
    return "Guest"
