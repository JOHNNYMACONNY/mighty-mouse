import unittest
import os
import file_utils
import io
from contextlib import redirect_stdout

class TestLocking(unittest.TestCase):
    def setUp(self):
        self.log = "test.log"
        self.lock = "test.log.lock"
        if os.path.exists(self.log): os.remove(self.log)
        if os.path.exists(self.lock): os.remove(self.lock)

    def test_basic_append(self):
        file_utils.atomic_append(self.log, "line1")
        with open(self.log, "r") as f:
            self.assertEqual(f.read(), "line1\n")
        self.assertFalse(os.path.exists(self.lock), "Lock file should be removed")

    def test_lock_retry(self):
        with open(self.lock, "w") as f: f.write("LOCKED")
        f = io.StringIO()
        with redirect_stdout(f):
            try:
                file_utils.atomic_append(self.log, "line2")
            except:
                pass
        output = f.getvalue()
        self.assertGreaterEqual(output.count("LOCK_HELD_RETRYING"), 5)

if __name__ == "__main__":
    unittest.main()
