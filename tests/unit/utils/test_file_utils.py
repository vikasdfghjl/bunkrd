"""
Unit tests for file utility functions.
"""
import os
import unittest
from unittest import mock
import tempfile
import shutil
from bunkrdownloader.utils.file_utils import (
    get_url_data, get_and_prepare_download_path, 
    write_url_to_list, get_already_downloaded_url,
    mark_as_downloaded, remove_illegal_chars
)


class TestFileUtils(unittest.TestCase):
    """Test cases for file utility functions."""

    def setUp(self):
        """Set up test environment before each test."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up after each test."""
        shutil.rmtree(self.temp_dir)
    
    def test_get_url_data(self):
        """Test parsing URL data."""
        # Test with normal URL
        url = "https://example.com/path/file.jpg"
        data = get_url_data(url)
        self.assertEqual(data["file_name"], "file.jpg")
        self.assertEqual(data["extension"], ".jpg")
        self.assertEqual(data["hostname"], "example.com")
        
        # Test with URL with no extension
        url = "https://example.com/path/file"
        data = get_url_data(url)
        self.assertEqual(data["file_name"], "file")
        self.assertEqual(data["extension"], "")
        
        # Test with malformed URL - no need to check for print calls
        # since the implementation handles errors without printing
        data = get_url_data("not a url")
        self.assertEqual(data["file_name"], "not a url")
    
    def test_get_and_prepare_download_path(self):
        """Test preparing download paths."""
        # Test with album name
        path = get_and_prepare_download_path(self.temp_dir, "test_album")
        expected_path = os.path.join(self.temp_dir, "test_album")
        self.assertEqual(path, expected_path)
        self.assertTrue(os.path.isdir(expected_path))
        self.assertTrue(os.path.isfile(os.path.join(expected_path, "already_downloaded.txt")))
        
        # Test with no album name but with base_path
        path = get_and_prepare_download_path(self.temp_dir, None)
        self.assertEqual(path, self.temp_dir)  # Should use the provided base_path
        
        # Test with no album name and no base_path
        path = get_and_prepare_download_path(None, None)
        self.assertEqual(path, "downloads")  # Should use the default path
    
    def test_write_url_to_list(self):
        """Test writing URLs to list file."""
        url = "https://example.com/test.jpg"
        result = write_url_to_list(url, self.temp_dir)
        self.assertTrue(result)
        
        list_file_path = os.path.join(self.temp_dir, "url_list.txt")
        self.assertTrue(os.path.isfile(list_file_path))
        
        with open(list_file_path, 'r') as f:
            content = f.read()
        self.assertIn(url, content)
    
    def test_get_already_downloaded_url(self):
        """Test reading already downloaded URLs."""
        # Create file with test URLs
        file_path = os.path.join(self.temp_dir, "already_downloaded.txt")
        test_urls = [
            "https://example.com/file1.jpg",
            "https://example.com/file2.jpg"
        ]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(test_urls))
        
        # Test reading them back
        urls = get_already_downloaded_url(self.temp_dir)
        self.assertEqual(urls, test_urls)
        
        # Test with non-existent file
        urls = get_already_downloaded_url(os.path.join(self.temp_dir, "non_existent"))
        self.assertEqual(urls, [])
    
    def test_mark_as_downloaded(self):
        """Test marking URLs as downloaded."""
        url = "https://example.com/test.jpg"
        result = mark_as_downloaded(url, self.temp_dir)
        self.assertTrue(result)
        
        # Check if URL was added to the file
        file_path = os.path.join(self.temp_dir, "already_downloaded.txt")
        with open(file_path, 'r') as f:
            content = f.read()
        self.assertIn(url, content)
    
    def test_remove_illegal_chars(self):
        """Test removing illegal characters from strings."""
        # Test with illegal characters
        test_string = 'File: with "illegal" chars? <test> |name|'
        result = remove_illegal_chars(test_string)
        self.assertEqual(result, 'File- with -illegal- chars- -test- -name-')
        
        # Test with empty string
        self.assertEqual(remove_illegal_chars(""), "unnamed")
        
        # Test with None
        self.assertEqual(remove_illegal_chars(None), "unnamed")


if __name__ == '__main__':
    unittest.main()