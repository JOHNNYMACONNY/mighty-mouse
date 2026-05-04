import unittest
from processor import Processor

class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.p = Processor()

    def test_existing_method(self):
        self.assertEqual(self.p.process_data("ok"), "Processed: ok")

    def test_dynamic_fallback(self):
        res = self.p.process_legacy_v1("some_data", flag=True)
        self.assertIsNone(res, "Fallback should return None")

    def test_attribute_error(self):
        with self.assertRaises(AttributeError):
            _ = self.p.something_else

if __name__ == "__main__":
    unittest.main()
