class Cache:
    def __init__(self):
        self.store = {}
    def update(self, key, value):
        self.store[key] = value
    def delete(self, key):
        if key in self.store:
            del self.store[key]
    def get(self, key):
        return self.store.get(key)

class Database:
    def __init__(self):
        self.data = {}
    def save(self, key, value):
        if value == "FAIL":
            raise RuntimeError("DB Write Error")
        self.data[key] = value
    def get(self, key):
        return self.data.get(key)
