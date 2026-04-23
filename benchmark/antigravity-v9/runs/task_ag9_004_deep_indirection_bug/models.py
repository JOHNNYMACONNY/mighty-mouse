class Record:
    def __init__(self, data):
        self.data = data
        # Fixed: Initialize status attribute to 'PENDING' to prevent AttributeError in router.py
        self.status = "PENDING"
