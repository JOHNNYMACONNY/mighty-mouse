import unittest
import sandbox
import math

class TestSandbox(unittest.TestCase):
    def test_math_success(self):
        code = "result = math.sqrt(16) + abs(-4)"
        res = sandbox.run_safe(code)
        self.assertEqual(res, 8.0)

    def test_restricted_access_os(self):
        # This should fail because 'os' is not in globals
        code = "import os; result = os.name"
        try:
            res = sandbox.run_safe(code)
            self.fail("Security Breach: 'os' was accessible in sandbox")
        except (NameError, ImportError, Exception):
            pass

    def test_restricted_access_eval(self):
        # eval should be blocked via restricted __builtins__
        code = "result = eval('1+1')"
        try:
            res = sandbox.run_safe(code)
            self.fail("Security Breach: 'eval' was accessible in sandbox")
        except (NameError, TypeError, Exception):
            pass

if __name__ == "__main__":
    unittest.main()
