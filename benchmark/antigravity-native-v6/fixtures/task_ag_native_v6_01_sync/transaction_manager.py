from components import Cache, Database

class TransactionManager:
    def __init__(self, cache, db):
        self.cache = cache
        self.db = db

    def update(self, key, value):
        # MISSION: Update cache, then DB. 
        # If DB fails, rollback cache for that key.
        self.cache.update(key, value)
        try:
            self.db.save(key, value)
        except Exception:
            self.cache.delete(key)
            raise
