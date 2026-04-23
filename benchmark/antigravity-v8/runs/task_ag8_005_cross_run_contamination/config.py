class AppConfig:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.values = {}
        return cls._instance
    
    def set(self, k, v):
        self.values[k] = v
    
    def get(self, k):
        return self.values.get(k)
    
    def clear(self):
        # Resets the state for the singleton instance
        self.values.clear()
