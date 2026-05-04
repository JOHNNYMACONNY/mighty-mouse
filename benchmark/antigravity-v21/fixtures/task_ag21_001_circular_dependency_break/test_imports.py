import unittest
import sys
import os

# Ensure current directory is in path
sys.path.append(os.getcwd())

class TestImports(unittest.TestCase):
    def test_import_cycle(self):
        try:
            # Clear previous modules if any
            for m in ['user_service', 'auth_service']:
                if m in sys.modules:
                    del sys.modules[m]
            
            # This should trigger the cycle and fail at baseline
            import auth_service
            import user_service
            
            # Verify functional logic
            self.assertEqual(user_service.get_user_name("123"), "User_123")
            self.assertEqual(auth_service.authenticate("123", "token"), "Authenticated User_123")
            
        except ImportError as e:
            # On some systems/python versions, it might be an AttributeError or similar during partial module init
            self.fail(f"IMPORT ERROR: Circular dependency detected: {e}")
        except Exception as e:
            # Catching AttributeError which often happens in circular imports (partially initialized module)
            if "has no attribute" in str(e):
                self.fail(f"CIRCULAR IMPORT ERROR: Partially initialized module access failed: {e}")
            raise e

if __name__ == "__main__":
    unittest.main()
