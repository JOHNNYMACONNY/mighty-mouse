# profile.py
from utils.validators import enforce_strict_types

@enforce_strict_types
class UserProfile:
    def __init__(self, username, email):
        self.username = username
        self.email = email
