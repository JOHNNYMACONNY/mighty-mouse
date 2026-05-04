import unittest
from multiprocessing import Pipe
import relay
import io
from contextlib import redirect_stdout
import threading

class TestRelay(unittest.TestCase):
    def test_successful_relay(self):
        parent, child = Pipe()
        def worker():
            if child.poll(2):
                msg = child.recv()
                child.send("ACK")
        t = threading.Thread(target=worker)
        t.start()
        res = relay.relay_message(parent, "hello")
        self.assertTrue(res)
        t.join()

    def test_timeout_relay(self):
        parent, child = Pipe()
        f = io.StringIO()
        with redirect_stdout(f):
            res = relay.relay_message(parent, "silent")
        self.assertFalse(res)
        self.assertIn("RELAY_TIMEOUT", f.getvalue())

if __name__ == "__main__":
    unittest.main()
