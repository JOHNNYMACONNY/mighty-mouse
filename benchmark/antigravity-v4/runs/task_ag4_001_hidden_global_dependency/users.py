_active_users = []

def get_users():
    # Return a COPY to prevent accidental mutation from external callers.
    return _active_users[:]

def register_user(name):
    # Use the global list directly to ensure updates are persisted
    global _active_users
    _active_users.append(name)
