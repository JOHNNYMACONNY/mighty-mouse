import unittest
import sys
import redirector

class TestDynamicRedirect(unittest.TestCase):
    def test_dynamic_updates(self):
        r = redirector.get_redirector()
        r.add_mapping("api", "modern_v1")
        if "api" in sys.modules: del sys.modules["api"]
        import api
        self.assertEqual(api.VAL, "V1")
        r.add_mapping("api", "modern_v2")
        if "api" in sys.modules: del sys.modules["api"]
        import api
        self.assertEqual(api.VAL, "V2")

if __name__ == "__main__":
    unittest.main()
