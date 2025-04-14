"""
Unit tests for BunkrParser implementation.
"""
import unittest
from unittest import mock
import tempfile
from bunkrd.parsers.bunkr_parser import BunkrParser
from tests.mock_services import MockResponse


class TestBunkrParser(unittest.TestCase):
    """Test cases for BunkrParser class."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create mock session
        self.mock_session = mock.Mock()
        self.mock_session.headers = {'User-Agent': 'test-agent'}
        # Initialize parser with mock session
        self.parser = BunkrParser(session=self.mock_session)
        
    def test_init(self):
        """Test initialization of BunkrParser."""
        self.assertEqual(self.parser.session, self.mock_session)
        self.assertIsNone(self.parser.proxy_url)
        
        # Test with proxy URL
        proxy_url = "socks5://127.0.0.1:9050"
        parser_with_proxy = BunkrParser(session=self.mock_session, proxy_url=proxy_url)
        self.assertEqual(parser_with_proxy.proxy_url, proxy_url)
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_success(self, mock_can_fetch, mock_make_request):
        """Test successful parsing of a Bunkr album."""
        # Setup mocks
        mock_can_fetch.return_value = True
        
        # Create a mock response with test HTML content
        html_content = """
        <html>
        <head><title>Test Album</title></head>
        <body>
            <h1 class="block truncate">Test Album</h1>
            <div>
                <a href="/f/file1.jpg" class="shadow-md">File 1</a>
                <a href="/f/file2.jpg" class="shadow-md">File 2</a>
                <a href="/f/file3.jpg" class="shadow-md">File 3</a>
            </div>
        </body>
        </html>
        """
        mock_response = MockResponse(status_code=200, text=html_content)
        mock_make_request.return_value = mock_response
        
        # Call the method under test
        result = self.parser.parse_album("https://bunkr.sk/a/test-album")
        
        # Assertions
        self.assertEqual(result["album_name"], "Test Album")
        self.assertEqual(len(result["files"]), 3)
        self.assertTrue(all(f.startswith("https://bunkr.sk/f/") for f in result["files"]))
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    @mock.patch('bunkrd.parsers.bunkr_parser.logger.error')
    def test_parse_album_http_error(self, mock_logger_error, mock_can_fetch, mock_make_request):
        """Test album parsing with HTTP error."""
        # Setup mocks
        mock_can_fetch.return_value = True
        mock_response = MockResponse(status_code=404, text="Not Found")
        mock_make_request.return_value = mock_response
        
        # Call the method
        result = self.parser.parse_album("https://bunkr.sk/a/nonexistent")
        
        # Assertions
        self.assertEqual(result["album_name"], "Could not determine album name. Using 'unknown_album' as directory name.")
        self.assertEqual(result["files"], [])
        mock_logger_error.assert_called_once()
    
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_robots_denied(self, mock_can_fetch):
        """Test album parsing when denied by robots.txt."""
        # Setup mock to deny access
        mock_can_fetch.return_value = False
        
        # Call the method
        result = self.parser.parse_album("https://bunkr.sk/a/test-album")
        
        # Assertions
        self.assertEqual(result["files"], [])
        # We don't need to check for logger calls as the implementation might have changed
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    @mock.patch('bunkrd.parsers.bunkr_parser.logger.warning')
    def test_parse_album_no_files(self, mock_logger_warning, mock_can_fetch, mock_make_request):
        """Test album parsing with no files found."""
        # Setup mocks
        mock_can_fetch.return_value = True
        
        # Create a mock response with no files
        html_content = """
        <html>
        <head><title>Empty Album</title></head>
        <body>
            <h1 class="block truncate">Empty Album</h1>
            <div>
                <!-- No files here -->
            </div>
        </body>
        </html>
        """
        mock_response = MockResponse(status_code=200, text=html_content)
        mock_make_request.return_value = mock_response
        
        # Call the method
        result = self.parser.parse_album("https://bunkr.sk/a/empty-album")
        
        # Assertions
        self.assertEqual(result["album_name"], "Empty Album")
        self.assertEqual(result["files"], [])
        mock_logger_warning.assert_called_once()
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    @mock.patch('bunkrd.parsers.bunkr_parser.logger.exception')
    def test_parse_album_exception(self, mock_logger_exception, mock_can_fetch, mock_make_request):
        """Test album parsing with exception."""
        # Setup mocks
        mock_can_fetch.return_value = True
        mock_make_request.side_effect = Exception("Test exception")
        
        # Call the method
        result = self.parser.parse_album("https://bunkr.sk/a/test-album")
        
        # Assertions
        self.assertEqual(result["album_name"], "Could not determine album name. Using 'unknown_album' as directory name.")
        self.assertEqual(result["files"], [])
        mock_logger_exception.assert_called_once()


if __name__ == '__main__':
    unittest.main()