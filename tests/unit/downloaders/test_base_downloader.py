"""
Unit tests for the BaseDownloader class.
"""
import os
import unittest
from unittest import mock
import tempfile
import requests
from bunkrdownloader.downloaders.base_downloader import BaseDownloader


class TestBaseDownloader(unittest.TestCase):
    """Test cases for BaseDownloader class."""

    def setUp(self):
        """Set up test environment before each test."""
        self.temp_dir = tempfile.mkdtemp()
        # Create mock session
        self.mock_session = mock.Mock()
        self.mock_session.headers = {'User-Agent': 'test-agent'}
        # Initialize downloader with mock session
        self.downloader = BaseDownloader(session=self.mock_session)

    def tearDown(self):
        """Clean up after each test."""
        # Remove temp directory and all its contents
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for file in files:
                os.remove(os.path.join(root, file))
            for dir in dirs:
                os.rmdir(os.path.join(root, dir))
        os.rmdir(self.temp_dir)
    
    def test_init(self):
        """Test the initialization of BaseDownloader."""
        self.assertEqual(self.downloader.session, self.mock_session)
        self.assertIsNone(self.downloader.proxy_url)
        
        # Test with proxy URL
        proxy_url = "socks5://127.0.0.1:9050"
        downloader_with_proxy = BaseDownloader(session=self.mock_session, proxy_url=proxy_url)
        self.assertEqual(downloader_with_proxy.proxy_url, proxy_url)
    
    def test_refresh_session(self):
        """Test refreshing the session with a new user agent."""
        with mock.patch('bunkrdownloader.downloaders.base_downloader.get_random_user_agent') as mock_get_ua:
            mock_get_ua.return_value = 'new-user-agent'
            self.downloader.refresh_session()
            self.assertEqual(self.mock_session.headers['User-Agent'], 'new-user-agent')
    
    @mock.patch('bunkrdownloader.downloaders.base_downloader.make_request_with_rate_limit')
    def test_make_api_request(self, mock_make_request):
        """Test making an API request."""
        mock_response = mock.Mock()
        mock_make_request.return_value = mock_response
        
        response = self.downloader.make_api_request('get', 'https://example.com')
        self.assertEqual(response, mock_response)
        mock_make_request.assert_called_once()

    @mock.patch('bunkrdownloader.downloaders.base_downloader.can_fetch')
    @mock.patch('bunkrdownloader.downloaders.base_downloader.sleep_with_random_delay')
    @mock.patch('bunkrdownloader.downloaders.base_downloader.get_url_data')
    @mock.patch('bunkrdownloader.downloaders.base_downloader.mark_as_downloaded')
    def test_download_success(self, mock_mark_downloaded, mock_get_url_data, 
                             mock_sleep, mock_can_fetch):
        """Test successful file download."""
        # Mock necessary functions
        mock_can_fetch.return_value = True
        mock_get_url_data.return_value = {'file_name': 'test_file.jpg'}
        mock_mark_downloaded.return_value = True
        
        # Import and use MockResponse from our mock_services instead of using mock.Mock()
        from tests.mock_services import MockResponse
        
        # Create a mock response with content
        mock_response = MockResponse(
            status_code=200,
            content=b'chunk1chunk2',
            headers={'content-length': '100'}
        )
        
        # Setup the mock session to return our MockResponse
        self.mock_session.get.return_value = mock_response
        
        # Create a mock open function
        mock_file = mock.mock_open()
        
        # Mock os.path.exists to return False (file doesn't exist)
        with mock.patch('os.path.exists', return_value=False):
            # Mock os.stat to return a file size object
            with mock.patch('os.stat') as mock_stat:
                mock_stat.return_value = mock.Mock(st_size=100)
                # Mock os.fsync to do nothing
                with mock.patch('os.fsync'):
                    # Mock os.rename to do nothing
                    with mock.patch('os.rename'):
                        # Test the download function with mocked file open
                        with mock.patch('builtins.open', mock_file):
                            result = self.downloader.download('https://example.com/test.jpg', self.temp_dir)
                            self.assertTrue(result)
                            mock_mark_downloaded.assert_called_once()
            
    @mock.patch('bunkrdownloader.downloaders.base_downloader.can_fetch')
    @mock.patch('bunkrdownloader.downloaders.base_downloader.sleep_with_random_delay')
    def test_download_denied_by_robots(self, mock_sleep, mock_can_fetch):
        """Test download denied by robots.txt."""
        mock_can_fetch.return_value = False
        
        result = self.downloader.download('https://example.com/test.jpg', self.temp_dir)
        self.assertFalse(result)
        self.mock_session.get.assert_not_called()
    
    def test_download_with_retry(self):
        """Test download with retry functionality."""
        with mock.patch.object(self.downloader, 'download') as mock_download:
            # First attempt fails, second succeeds
            mock_download.side_effect = [False, True]
            
            result = self.downloader.download_with_retry(
                'https://example.com/test.jpg', 
                self.temp_dir,
                retries=2
            )
            
            self.assertTrue(result)
            self.assertEqual(mock_download.call_count, 2)
            
            # All attempts fail
            mock_download.reset_mock()
            mock_download.side_effect = [False, False, False]
            
            result = self.downloader.download_with_retry(
                'https://example.com/test.jpg', 
                self.temp_dir,
                retries=3
            )
            
            self.assertFalse(result)
            self.assertEqual(mock_download.call_count, 3)


if __name__ == '__main__':
    unittest.main()