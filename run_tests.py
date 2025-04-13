#!/usr/bin/env python
"""
Test runner for BunkrDownloader.

This script discovers and runs all tests in the project.
Run with -v flag for verbose output.
"""
import unittest
import sys


if __name__ == "__main__":
    # Discover all tests in the tests/ directory
    test_suite = unittest.defaultTestLoader.discover('tests')
    
    # Get verbosity level from command line arguments
    verbosity = 2 if '-v' in sys.argv or '--verbose' in sys.argv else 1
    
    # Run the test suite
    result = unittest.TextTestRunner(verbosity=verbosity).run(test_suite)
    
    # Exit with appropriate code based on test results
    sys.exit(0 if result.wasSuccessful() else 1)