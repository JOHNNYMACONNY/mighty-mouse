_active_users = []

def get_users():
    # This currently returns the reference. 
    # Change it to return a COPY to prevent accidental mutation.
    return _active_users

def register_user(name):
    users = get_users()
    users.append(name)
