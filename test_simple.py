import unittest
from logic.processor import RepositoryProcessor

class TestSimple(unittest.TestCase):
    def test_processor_exists(self):
        processor = RepositoryProcessor()
        self.assertIsNotNone(processor)

if __name__ == "__main__":
    unittest.main()
