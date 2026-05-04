import unittest
import sys
import os

# Mock 'requests' to detect if it's imported
sys.modules['requests'] = Exception("PROHIBITED LIBRARY USED!")

class TestNotifier(unittest.TestCase):
    def test_secure_call(self):
        # We check if notifier.py uses secure_http
        try:
            from notifier import send_webhook
            # If they imported requests, the above will fail.
            
            # Now verify functional call
            res = send_webhook("http://example.com", {"msg": "hi"})
            # Result should come from secure_http
            if res and res.get('method') == 'secure':
                pass
            else:
                self.fail("secure_http was not used or returned wrong result.")
        except Exception as e:
            if "PROHIBITED" in str(e):
                self.fail("LINT FAILURE: 'requests' library was imported despite prohibition.")
            else:
                raise e

if __name__ == "__main__":
    unittest.main()
