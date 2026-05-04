import unittest
import patcher

def target():
    return "ORIGINAL"

def replacement():
    return "FIXED"

class TestPatch(unittest.TestCase):
    def test_bytecode_replacement(self):
        original_id = id(target)
        patcher.hotfix(target, replacement)
        self.assertEqual(id(target), original_id)
        self.assertEqual(target(), "FIXED")

if __name__ == "__main__":
    unittest.main()
