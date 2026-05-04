import unittest
import data_store
import event_bus
import manager

class TestAsyncIntegrity(unittest.TestCase):
    def setUp(self):
        data_store.set_val("1", "old_val")
        event_bus.set_fail(False)

    def test_success(self):
        manager.update_with_event("1", "new_val")
        self.assertEqual(data_store.get_val("1"), "new_val")

    def test_rollback(self):
        event_bus.set_fail(True)
        try:
            manager.update_with_event("1", "failed_val")
        except Exception as e:
            self.assertIn("EVENT_BUS_FAILURE", str(e))
        
        # Should be rolled back to "old_val"
        self.assertEqual(data_store.get_val("1"), "old_val")

if __name__ == "__main__":
    unittest.main()
