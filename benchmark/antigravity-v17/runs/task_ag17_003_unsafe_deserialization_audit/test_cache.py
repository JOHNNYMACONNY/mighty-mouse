import unittest
import sys
import os

# Mock pickle to detect usage
sys.modules['pickle'] = Exception("PROHIBITED LIBRARY USED!")

class TestCache(unittest.TestCase):
    def test_json_serialization(self):
        try:
            from cache_manager import save_session, load_session
            
            data = {"user_id": 123, "name": "Alice"}
            serialized = save_session(data)
            
            # Check if it's JSON (should be a string or bytes that look like JSON)
            import json
            # JSON might be bytes if encoded
            decoded = serialized.decode('utf-8') if isinstance(serialized, bytes) else serialized
            self.assertEqual(json.loads(decoded), data)
            
            # Test loading
            self.assertEqual(load_session(serialized), data)
            
        except Exception as e:
            if "PROHIBITED" in str(e):
                self.fail("SECURITY FAILURE: 'pickle' library was used despite prohibition.")
            else:
                raise e

    def test_corrupted_data(self):
        from cache_manager import load_session
        self.assertEqual(load_session("invalid data"), {})

if __name__ == "__main__":
    unittest.main()
