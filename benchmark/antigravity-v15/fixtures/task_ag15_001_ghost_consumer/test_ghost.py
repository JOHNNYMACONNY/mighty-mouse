import unittest
import sys
import os

# Add paths
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

class TestGhostConsumer(unittest.TestCase):
    def test_consumer_not_broken(self):
        try:
            from ghost.consumer import process_item
            name = process_item()
            self.assertEqual(name, "Test Item")
        except TypeError as e:
            self.fail(f"SCHEMA BREAKAGE: The ghost consumer was broken by your change! {e}. You must provide a default value for the new field.")

    def test_new_field_exists(self):
        from api.schemas import ItemSchema
        it = ItemSchema("Test", priority=10)
        self.assertEqual(it.priority, 10)

if __name__ == "__main__":
    unittest.main()
