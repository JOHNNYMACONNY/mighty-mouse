import unittest
from auth_service import is_authorized

class TestAuth(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(is_authorized(["admin", "user"], "admin"))
        self.assertTrue(is_authorized(["user", "viewer"], "viewer"))
        
    def test_escalation_prevention(self):
        # A user with 'guest_admin' should not pass for 'admin'
        self.assertFalse(is_authorized(["guest_admin"], "admin"), "ESCALATION DETECTED: guest_admin passed for admin")
        # A user with 'super_editor' should not pass for 'editor'
        self.assertFalse(is_authorized(["super_editor"], "editor"), "ESCALATION DETECTED: super_editor passed for editor")

    def test_missing_role(self):
        self.assertFalse(is_authorized(["user"], "admin"))

if __name__ == "__main__":
    unittest.main()
