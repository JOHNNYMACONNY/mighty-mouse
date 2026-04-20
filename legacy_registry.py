class LegacyRegistryRateLimiter:
    def __init__(self): self.state = 'INIT'
    def process(self, data):
        # Procedural logic for Legacy Registry RateLimiter
        return data[::-1] if isinstance(data, str) else data