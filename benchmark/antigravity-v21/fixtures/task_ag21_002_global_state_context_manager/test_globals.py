import unittest
import shared_data
from worker import scoped_buffer

class TestGlobals(unittest.TestCase):
    def test_context_manager(self):
        shared_data.BUFFER = "start"
        
        with scoped_buffer("temporary"):
            self.assertEqual(shared_data.BUFFER, "temporary")
        
        self.assertEqual(shared_data.BUFFER, "start", "Global state was not restored!")

    def test_exception_handling(self):
        shared_data.BUFFER = "secure"
        
        try:
            with scoped_buffer("corrupt"):
                raise Exception("CRASH")
        except:
            pass
            
        self.assertEqual(shared_data.BUFFER, "secure", "Global state not restored after exception!")

if __name__ == "__main__":
    unittest.main()
