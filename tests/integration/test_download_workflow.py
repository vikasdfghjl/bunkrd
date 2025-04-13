"""
Integration test for the download workflow.

This test demonstrates how multiple components work together to download files.
It uses mock services to avoid real network calls.
"""
import unittest
import os
import tempfile
import shutil
from unittest import mock
from bunkrdownloader.controller import DownloadController
from tests.mock_services import MockRequestsSession


class TestDownloadWorkflow(unittest.TestCase):
    """Test the full download workflow."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temp directory for downloads
        self.temp_dir = tempfile.mkdtemp()
        
        # Create mock services
        self.mock_session = MockRequestsSession()
        
        # Patch the requests.Session to use our mock
        self.session_patcher = mock.patch('requests.Session', return_value=self.mock_session)
        self.session_patcher.start()
        
        # Mock the decrypt_with_key function to always return a valid URL
        self.decrypt_patcher = mock.patch('bunkrdownloader.utils.security_utils.decrypt_with_key', 
                                         return_value='https://example.com/decrypted-test-url')
        self.decrypt_patcher.start()
        
        # Mock the BaseDownloader.download method to always return True
        self.download_patcher = mock.patch('bunkrdownloader.downloaders.base_downloader.BaseDownloader.download',
                                          return_value=True)
        self.download_patcher.start()
        
        # Mock the BunkrDownloader.get_real_download_url method to return a valid URL
        self.get_url_patcher = mock.patch('bunkrdownloader.downloaders.bunkr_downloader.BunkrDownloader.get_real_download_url',
                                         return_value={'url': 'https://example.com/decrypted-test-url', 'size': 1024})
        self.get_url_patcher.start()
        
        # Create controller with default settings
        self.controller = DownloadController()
    
    def tearDown(self):
        """Clean up after tests."""
        # Stop patchers
        self.session_patcher.stop()
        self.decrypt_patcher.stop()
        self.download_patcher.stop()
        self.get_url_patcher.stop()
        
        # Remove temp directory
        shutil.rmtree(self.temp_dir)
    
    def test_process_url_file(self):
        """Test processing a single file URL."""
        # Test URL for a file (matches the mock service's test files)
        url = "https://bunkr.sk/f/test-file1"
        
        # Process the URL
        with mock.patch('builtins.print'):  # Suppress print output
            result = self.controller.process_url(url, self.temp_dir)
        
        # Assert successful download
        self.assertTrue(result)
        
        # Check that the URL was marked as downloaded
        already_downloaded_path = os.path.join(self.temp_dir, "already_downloaded.txt")
        self.assertTrue(os.path.exists(already_downloaded_path))
        
        with open(already_downloaded_path, 'r') as f:
            content = f.read()
            self.assertIn(url, content)
    
    def test_process_album_url(self):
        """Test processing an album URL."""
        # Test URL for an album (matches the mock service's test album)
        url = "https://bunkr.sk/a/test-album"
        
        # Mock the parse_album method to return test data
        with mock.patch('bunkrdownloader.parsers.bunkr_parser.BunkrParser.parse_album') as mock_parse:
            mock_parse.return_value = {
                "album_name": "Test Album", 
                "files": ["https://bunkr.sk/f/test-file1", "https://bunkr.sk/f/test-file2"]
            }
            
            # Process the URL
            with mock.patch('builtins.print'):  # Suppress print output
                with mock.patch('tqdm.tqdm'):   # Suppress progress bar
                    result = self.controller.process_url(url, self.temp_dir)
        
        # Assert successful album processing
        self.assertTrue(result)
        
        # Album should create a directory with the album name
        album_dir = os.path.join(self.temp_dir, "Test Album")
        self.assertTrue(os.path.exists(album_dir))
        
        # Check that already_downloaded.txt contains the file URLs
        already_downloaded_path = os.path.join(album_dir, "already_downloaded.txt")
        self.assertTrue(os.path.exists(already_downloaded_path))
    
    def test_process_file_with_urls(self):
        """Test processing a file containing URLs."""
        # Create a temporary file with test URLs
        urls_file = os.path.join(self.temp_dir, "test_urls.txt")
        with open(urls_file, 'w') as f:
            f.write("https://bunkr.sk/f/test-file1\n")
            f.write("https://bunkr.sk/f/test-file2\n")
        
        # Process the file
        with mock.patch('builtins.print'):  # Suppress print output
            with mock.patch('tqdm.tqdm'):   # Suppress progress bar
                result = self.controller.process_file(urls_file, self.temp_dir)
        
        # Assert successful processing
        self.assertTrue(result)
        
        # Check that both URLs were marked as downloaded
        already_downloaded_path = os.path.join(self.temp_dir, "already_downloaded.txt")
        self.assertTrue(os.path.exists(already_downloaded_path))
        
        with open(already_downloaded_path, 'r') as f:
            content = f.read()
            self.assertIn("https://bunkr.sk/f/test-file1", content)
            self.assertIn("https://bunkr.sk/f/test-file2", content)


if __name__ == '__main__':
    unittest.main()