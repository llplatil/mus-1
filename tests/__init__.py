"""Test suite for MUS1"""

import unittest

def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    start_dir = '.'
    suite = loader.discover(start_dir)
    runner = unittest.TextTestRunner()
    runner.run(suite)

if __name__ == '__main__':
    run_tests()
