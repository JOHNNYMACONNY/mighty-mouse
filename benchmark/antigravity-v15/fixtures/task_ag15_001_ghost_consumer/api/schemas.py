# schemas.py
class ItemSchema:
    def __init__(self, name, priority=0):
        self.name = name
        self.priority = priority
