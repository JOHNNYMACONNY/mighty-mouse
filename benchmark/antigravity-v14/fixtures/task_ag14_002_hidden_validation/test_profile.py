import unittest
from profile import UserProfile

class TestProfile(unittest.TestCase):
    def test_add_nickname(self):
        # This will fail if nickname is added WITHOUT a type hint
        try:
            u = UserProfile("bobby", "b@example.com")
            # The agent should have added nickname=... in __init__ and a type hint
            # If they just added self.nickname = ... without nickname: str, this fails.
            if hasattr(u, 'nickname'):
                pass
            else:
                self.fail("nickname attribute not added.")
        except TypeError as e:
            self.fail(f"Validation failed: {e}. Did you forget the type annotation?")

if __name__ == "__main__":
    unittest.main()
