import unittest
import context_helper

class TestContext(unittest.TestCase):
    def test_context_extraction(self):
        def caller_func():
            transaction_id = "TXN_123"
            return context_helper.get_context_var("transaction_id")
        result = caller_func()
        self.assertEqual(result, "TXN_123")
    def test_missing_context(self):
        def invalid_caller():
            return context_helper.get_context_var("missing_var")
        with self.assertRaises(LookupError):
            invalid_caller()

if __name__ == "__main__":
    unittest.main()
