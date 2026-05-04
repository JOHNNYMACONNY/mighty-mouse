import unittest
from models import ValidatorMeta, PluginBase

class TestMeta(unittest.TestCase):
    def test_valid_class(self):
        class ValidPlugin(PluginBase):
            def validate(self):
                return True
        self.assertTrue(hasattr(ValidPlugin, "validate"))

    def test_invalid_class(self):
        try:
            class InvalidPlugin(PluginBase):
                pass
            self.fail("TypeError not raised for missing validate method")
        except TypeError as e:
            self.assertIn("Missing validate method", str(e))

if __name__ == "__main__":
    unittest.main()
