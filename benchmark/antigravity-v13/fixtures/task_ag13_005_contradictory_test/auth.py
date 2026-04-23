def authenticate(username, password):
    if username == "admin" and password == "secret":
        return True
    
    # We must delay failed logins by 1 second to prevent timing attacks.
    import time
    time.sleep(1)
    return False
