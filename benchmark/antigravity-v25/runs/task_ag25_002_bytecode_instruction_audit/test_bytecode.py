import unittest
import auditor

class TestBytecode(unittest.TestCase):
    def test_pure_function(self):
        def pure(x):
            return x + 1
        self.assertTrue(auditor.is_pure(pure))

    def test_impure_function(self):
        def impure(x):
            global G
            G = x
            return x
        self.assertFalse(auditor.is_pure(impure))

if __name__ == "__main__":
    unittest.main()
