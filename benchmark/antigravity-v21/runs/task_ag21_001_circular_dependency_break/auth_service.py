def is_logged_in(uid): return uid == '123'
def authenticate(uid, token):
    import user_service
    name = user_service.get_user_name(uid)
    return f'Authenticated {name}'