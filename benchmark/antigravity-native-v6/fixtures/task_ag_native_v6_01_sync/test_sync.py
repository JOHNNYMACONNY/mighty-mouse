from components import Cache, Database
from transaction_manager import TransactionManager

def test_sync_success():
    cache = Cache()
    db = Database()
    tm = TransactionManager(cache, db)
    
    tm.update("a", "data")
    assert cache.get("a") == "data"
    assert db.get("a") == "data"

def test_sync_rollback():
    cache = Cache()
    db = Database()
    tm = TransactionManager(cache, db)
    
    # 1. First set it successfully
    tm.update("b", "old")
    
    # 2. Try to update to "FAIL" which triggers DB error
    try:
        tm.update("b", "FAIL")
    except RuntimeError:
        pass
    
    # CRITICAL: Cache must NOT have "FAIL". 
    # In a perfect rollback it should have "old" or be deleted.
    # Requirement: "If DB fails, it must DELETE the key from the cache to ensure cache doesn't have stale data"
    assert cache.get("b") is None, "Cache should have deleted 'b' on failure"

if __name__ == "__main__":
    test_sync_success()
    test_sync_rollback()
    print("PASS")
