import unittest
import local_db
from transaction_manager import save_transaction

class TestRollback(unittest.TestCase):
    def test_rollback_on_failure(self):
        data = {"id": "tx123", "amount": 100, "trigger_fail": True}
        
        try:
            save_transaction(data)
        except Exception:
            pass # Expected
        
        # Verify local_db is clean
        self.assertIsNone(local_db.get("tx123"), "Local DB entry was not rolled back after remote failure!")

    def test_success_path(self):
        data = {"id": "tx456", "amount": 200, "trigger_fail": False}
        save_transaction(data)
        self.assertEqual(local_db.get("tx456"), data, "Local DB entry missing on success.")

if __name__ == "__main__":
    unittest.main()
