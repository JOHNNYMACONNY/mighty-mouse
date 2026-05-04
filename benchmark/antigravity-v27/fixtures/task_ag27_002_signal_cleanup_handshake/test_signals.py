import unittest
import signal
import os
import worker
import time
import io
from contextlib import redirect_stdout

class TestSignals(unittest.TestCase):
    def test_sigusr1_handler(self):
        worker.setup_signal_handler()
        f = io.StringIO()
        with redirect_stdout(f):
            os.kill(os.getpid(), signal.SIGUSR1)
            time.sleep(0.1)
        self.assertTrue(worker.TERMINATE_REQUESTED)
        self.assertIn("CLEANUP_INITIATED", f.getvalue())

if __name__ == "__main__":
    unittest.main()
