import unittest
import json
import gateway

class TestPropagation(unittest.TestCase):
    def test_timeout_propagation(self):
        # We expect the final output to reflect the new key and value
        # e.g. "Sent data with timeout 5000ms"
        res = gateway.start_request()
        self.assertIn("5000ms", res)
        self.assertNotIn(" 5s", res)

    def test_settings_key(self):
        with open('settings.json', 'r') as f:
            config = json.load(f)
        self.assertIn('request_timeout_ms', config)
        self.assertNotIn('timeout', config)

if __name__ == "__main__":
    unittest.main()
