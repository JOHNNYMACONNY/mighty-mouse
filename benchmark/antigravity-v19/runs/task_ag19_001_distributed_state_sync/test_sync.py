import unittest
from nodes import node_a, node_b, node_c
import coordinator

class TestSync(unittest.TestCase):
    def setUp(self):
        # Reset nodes to known state - IMPORTANT: reset failure flag BEFORE update
        node_c.set_fail(False)
        node_a.update_node("initial")
        node_b.update_node("initial")
        node_c.update_node("initial")

    def test_successful_sync(self):
        coordinator.update_all("new_value")
        self.assertEqual(node_a.get_node_data(), "new_value")
        self.assertEqual(node_b.get_node_data(), "new_value")
        self.assertEqual(node_c.get_node_data(), "new_value")

    def test_rollback_on_failure(self):
        # Force failure on the 3rd node
        node_c.set_fail(True)
        try:
            coordinator.update_all("crashed_value")
        except Exception as e:
            self.assertIn("NODE_C_FAILURE", str(e))
        
        # ALL nodes should still be "initial" if rollback worked
        self.assertEqual(node_a.get_node_data(), "initial", "Node A failed to rollback")
        self.assertEqual(node_b.get_node_data(), "initial", "Node B failed to rollback")
        self.assertEqual(node_c.get_node_data(), "initial", "Node C failed to rollback")

if __name__ == "__main__":
    unittest.main()
