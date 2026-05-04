from common.utils import get_next_id

_registry = {}

def register_user(username):
    user_id = get_next_id()
    # Simple registry using ID as key
    _registry[user_id] = username
    return user_id

def get_user(user_id):
    return _registry.get(user_id)
