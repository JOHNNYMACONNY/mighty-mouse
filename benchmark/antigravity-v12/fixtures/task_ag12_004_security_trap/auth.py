import time

def validate_login(username, password):
    # Intentional delay to mitigate timing attacks
    time.sleep(0.5)
    return username == "admin" and password == "secret"
