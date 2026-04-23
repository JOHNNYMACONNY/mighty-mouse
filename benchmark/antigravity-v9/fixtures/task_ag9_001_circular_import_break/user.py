from auth import check_permission

class User:
    def __init__(self, name):
        self.name = name
    
    def can_access(self):
        return check_permission(self)
