import unittest
import sys
import bootstrap

class TestImportRedirect(unittest.TestCase):
    def test_redirect(self):
        bootstrap.register_redirect()
        if "legacy_api" in sys.modules: del sys.modules["legacy_api"]
        try:
            import legacy_api
            self.assertEqual(legacy_api.VERSION, "MODERN")
        except ImportError:
            self.fail("Redirection failed")

if __name__ == "__main__":
    unittest.main()
