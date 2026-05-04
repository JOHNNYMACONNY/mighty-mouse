import unittest
import mmap
import os
import time
import threading
import mmap_comms

class TestMmap(unittest.TestCase):
    def setUp(self):
        self.filename = "buffer.dat"
        with open(self.filename, "wb") as f:
            f.write(b"\x00" * 1024)
    def tearDown(self):
        if os.path.exists(self.filename): os.remove(self.filename)
    def test_sync_communication(self):
        with open(self.filename, "r+b") as f:
            mm = mmap.mmap(f.fileno(), 0)
            results = []
            def reader():
                results.append(mmap_comms.read_data(mm))
            t = threading.Thread(target=reader)
            t.start()
            time.sleep(0.1)
            mmap_comms.write_data(mm, "SECRET")
            t.join()
            self.assertEqual(results[0], "SECRET")
            self.assertEqual(mm[0], 0)

if __name__ == "__main__":
    unittest.main()
