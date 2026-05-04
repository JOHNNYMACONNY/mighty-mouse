import unittest
from infrastructure import remote_service
from cache import local_store
import fetcher
import io
from contextlib import redirect_stdout

class TestResilience(unittest.TestCase):
    def setUp(self):
        local_store.set_cache(None)

    def test_success_first_try(self):
        remote_service.set_fail_config(0)
        res = fetcher.fetch_with_resilience()
        self.assertEqual(res, "FRESH_DATA")

    def test_retry_success(self):
        remote_service.set_fail_config(2) # Fails twice, should succeed on 3rd
        f = io.StringIO()
        with redirect_stdout(f):
            res = fetcher.fetch_with_resilience()
        
        self.assertEqual(res, "FRESH_DATA")
        output = f.getvalue()
        self.assertIn("RETRYING_IN_1S", output)
        self.assertIn("RETRYING_IN_2S", output)

    def test_fallback_to_cache(self):
        remote_service.set_fail_config(10) # Constant failure
        local_store.set_cache("STALE_DATA")
        
        res = fetcher.fetch_with_resilience()
        self.assertEqual(res, "STALE_DATA")

    def test_emergency_default(self):
        remote_service.set_fail_config(10)
        local_store.set_cache(None)
        
        res = fetcher.fetch_with_resilience()
        self.assertEqual(res, "EMERGENCY_DEFAULT")

if __name__ == "__main__":
    unittest.main()
