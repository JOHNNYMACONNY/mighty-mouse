import unittest
import security
import trusted_logic
import os

class TestAudit(unittest.TestCase):
    def test_untrusted_call(self):
        try:
            security.verify_caller()
            self.fail("PermissionError not raised for untrusted caller")
        except PermissionError as e:
            self.assertEqual(str(e), "UNTRUSTED_CALLER")

    def test_trusted_call(self):
        res = trusted_logic.trusted_operation()
        self.assertTrue(res)

if __name__ == "__main__":
    unittest.main()
