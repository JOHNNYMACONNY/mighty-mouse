import unittest
import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/mighty_mouse/orchestrator')))
from response_parser import ResponseParser

class TestParserHygiene(unittest.TestCase):
    def test_standard_block_passes(self):
        text = "```python:hello.py\nprint('hello world')\n```"
        res = ResponseParser.parse_and_write(text, workspace_root=self.workspace, strict_code_hygiene=True)
        self.assertEqual(res, ["hello.py"])
        with open(Path(self.workspace, "hello.py"), "r") as f:
            self.assertEqual(f.read(), "print('hello world')")

    def test_xml_outside_block_passes(self):
        text = "</thought>\n```python:hello.py\nprint('hello')\n```"
        res = ResponseParser.parse_and_write(text, workspace_root=self.workspace, strict_code_hygiene=True)
        self.assertEqual(res, ["hello.py"])

    def test_xml_inside_block_fails(self):
        text = "```python:hello.py\nprint('hello')\n</thought>\n```"
        with self.assertRaisesRegex(ValueError, "XML leakage detected"):
            ResponseParser.parse_and_write(text, workspace_root=self.workspace, strict_code_hygiene=True)

    def test_xml_inside_block_passes_when_not_strict(self):
        text = "```python:hello.py\nprint('hello')\n</thought>\n```"
        res = ResponseParser.parse_and_write(text, workspace_root=self.workspace, strict_code_hygiene=False)
        self.assertEqual(res, ["hello.py"])

    def test_ambiguous_content_fails_safely(self):
        # Even if it's in a comment, we want to reject it if it looks like orchestration leakage
        text = "```python:hello.py\n# This is a </thought> comment\n```"
        with self.assertRaisesRegex(ValueError, "XML leakage detected"):
            ResponseParser.parse_and_write(text, workspace_root=self.workspace, strict_code_hygiene=True)

    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="mighty-mouse-parser-")
        self.workspace = self._temporary.name

    def tearDown(self):
        self._temporary.cleanup()

if __name__ == "__main__":
    unittest.main()
