import unittest
import os

class TestGEMINIMandate(unittest.TestCase):
    def test_rule_3_exists(self):
        with open('GEMINI.md', 'r') as f:
            content = f.read()
        self.assertIn("Rule 3: Final File Review", content)

if __name__ == '__main__':
    unittest.main()
