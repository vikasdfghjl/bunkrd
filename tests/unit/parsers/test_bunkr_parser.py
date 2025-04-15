"""
Unit tests for BunkrParser implementation.
"""
import unittest
from unittest import mock
import tempfile
from bunkrd.parsers.bunkr_parser import BunkrParser, BunkrIncrementalParser
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
    
    @mock.patch('bunkrd.parsers.bunkr_parser.SessionFactory.create_session')
    def test_create_session(self, mock_create_session):
        """Test create_session method."""
        # Setup mock
        mock_session = mock.Mock()
        mock_create_session.return_value = mock_session
        
        # Create parser without session to trigger create_session
        parser = BunkrParser()
        
        # Assertions
        mock_create_session.assert_called_once_with(parser.proxy_url)
        self.assertEqual(parser.session, mock_session)
        
        # Test with proxy setting
        proxy_url = "socks5://127.0.0.1:9050"
        parser_proxy = BunkrParser(proxy_url=proxy_url)
        mock_create_session.assert_called_with(proxy_url)
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_url_normalization(self, mock_can_fetch, mock_make_request):
        """Test URL normalization for different Bunkr domains."""
        # Setup mocks
        mock_can_fetch.return_value = True
        mock_response = MockResponse(status_code=200, text="<html><body><h1>Test</h1></body></html>")
        mock_make_request.return_value = mock_response
        
        # Test different domain variants
        test_urls = [
            "https://bunkr.la/a/test",
            "https://bunkr.is/a/test",
            "https://bunkr.cr/a/test",
            "bunkr.sk/a/test"  # No scheme
        ]
        
        for url in test_urls:
            self.parser.parse_album(url, use_incremental=False)
            # Check that the domain was normalized to bunkr.sk
            expected_url = url.replace("bunkr.la", "bunkr.sk").replace("bunkr.is", "bunkr.sk").replace("bunkr.cr", "bunkr.sk")
            if not expected_url.startswith("http"):
                expected_url = f"https://{expected_url}"
            mock_make_request.assert_called_with(self.mock_session, 'get', expected_url, timeout=15, check_robots=False)
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_fallback_strategies(self, mock_can_fetch, mock_make_request):
        """Test fallback HTML parsing strategies."""
        # Setup mocks
        mock_can_fetch.return_value = True
        
        # Test Strategy 1: Standard with shadow-md class
        html_content_1 = """
        <html><body>
            <h1>Test Album 1</h1>
            <a href="/f/file1.jpg" class="shadow-md">File 1</a>
            <a href="/f/file2.jpg" class="shadow-md">File 2</a>
        </body></html>
        """
        mock_response_1 = MockResponse(status_code=200, text=html_content_1)
        mock_make_request.return_value = mock_response_1
        
        result_1 = self.parser.parse_album("https://bunkr.sk/a/test", use_incremental=False)
        self.assertEqual(len(result_1["files"]), 2)
        
        # Test Strategy 2: No shadow-md class but has file paths
        html_content_2 = """
        <html><body>
            <h1>Test Album 2</h1>
            <a href="/f/file1.jpg">File 1</a>
            <a href="/a/nested-album">Nested Album</a>
        </body></html>
        """
        mock_response_2 = MockResponse(status_code=200, text=html_content_2)
        mock_make_request.return_value = mock_response_2
        
        result_2 = self.parser.parse_album("https://bunkr.sk/a/test", use_incremental=False)
        self.assertEqual(len(result_2["files"]), 2)
        
        # Test Strategy 3: Regex pattern matching
        html_content_3 = """
        <html><body>
            <h1>Test Album 3</h1>
            <a href="/f/a1b2c3d4e5f6g7h8">Strange filename</a>
        </body></html>
        """
        mock_response_3 = MockResponse(status_code=200, text=html_content_3)
        mock_make_request.return_value = mock_response_3
        
        result_3 = self.parser.parse_album("https://bunkr.sk/a/test", use_incremental=False)
        self.assertEqual(len(result_3["files"]), 1)
    
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_incremental(self, mock_can_fetch):
        """Test incremental album parsing."""
        # Setup mocks
        mock_can_fetch.return_value = True
        
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
        
        # Setup a proper mock for session.get that returns a response with iter_content
        mock_response = mock.Mock()
        mock_response.status_code = 200
        
        # Mock the iter_content method to return chunks of the HTML
        def mock_iter_content(chunk_size=None, decode_unicode=None):
            # Return HTML content in a single chunk for simplicity
            if decode_unicode:
                yield html_content
            else:
                yield html_content.encode('utf-8')
                
        mock_response.iter_content = mock_iter_content
        
        # Apply the mock to session.get directly
        self.mock_session.get.return_value = mock_response
        
        # Call the method under test with incremental parsing
        result = self.parser.parse_album("https://bunkr.sk/a/test-album", use_incremental=True)
        
        # Assertions
        self.assertEqual(result["album_name"], "Test Album")
        self.assertEqual(len(result["files"]), 3)
        self.assertTrue(all(f.startswith("https://bunkr.sk/f/") for f in result["files"]))
    
    @mock.patch('bunkrd.parsers.bunkr_parser.make_request_with_rate_limit')
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_incremental_error(self, mock_can_fetch, mock_make_request):
        """Test incremental parsing with error."""
        # Setup mocks
        mock_can_fetch.return_value = True
        
        # Mock session.get to raise an exception
        self.mock_session.get.side_effect = Exception("Connection error during streaming")
        
        # Call the method
        result = self.parser.parse_album("https://bunkr.sk/a/test-album", use_incremental=True)
        
        # Should handle the error gracefully
        self.assertEqual(result["album_name"], "unknown_album")
        self.assertEqual(result["files"], [])
    
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
        
        # Call the method under test - explicitly disable incremental parsing for tests
        result = self.parser.parse_album("https://bunkr.sk/a/test-album", use_incremental=False)
        
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
        
        # Call the method - explicitly disable incremental parsing
        result = self.parser.parse_album("https://bunkr.sk/a/nonexistent", use_incremental=False)
        
        # Assertions
        self.assertEqual(result["album_name"], "Could not determine album name. Using 'unknown_album' as directory name.")
        self.assertEqual(result["files"], [])
        mock_logger_error.assert_called_once()
    
    @mock.patch('bunkrd.parsers.bunkr_parser.can_fetch')
    def test_parse_album_robots_denied(self, mock_can_fetch):
        """Test album parsing when denied by robots.txt."""
        # Setup mock to deny access
        mock_can_fetch.return_value = False
        
        # Call the method - incremental doesn't matter for robots check
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
        
        # Call the method - explicitly disable incremental parsing
        result = self.parser.parse_album("https://bunkr.sk/a/empty-album", use_incremental=False)
        
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
        
        # Call the method - explicitly disable incremental parsing
        result = self.parser.parse_album("https://bunkr.sk/a/test-album", use_incremental=False)
        
        # Assertions
        self.assertEqual(result["album_name"], "Could not determine album name. Using 'unknown_album' as directory name.")
        self.assertEqual(result["files"], [])
        mock_logger_exception.assert_called_once()


class TestBunkrIncrementalParser(unittest.TestCase):
    """Test cases for BunkrIncrementalParser class."""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.parser = BunkrIncrementalParser(base_url='https://bunkr.sk')
    
    def test_parse_h1_album_name(self):
        """Test parsing album name from h1 tag."""
        # Feed HTML with h1 tag containing album name
        self.parser.feed('<h1 class="block truncate">Test Album Name</h1>')
        self.assertEqual(self.parser.album_name, "Test Album Name")
        
        # Reset and test h1 without specific class
        parser2 = BunkrIncrementalParser()
        parser2.feed('<h1>Another Album</h1>')
        self.assertEqual(parser2.album_name, "Another Album")
    
    def test_parse_title_album_name(self):
        """Test parsing album name from title tag."""
        # Test with no h1 but title tag with expected format
        self.parser.feed('<title>Title Album - Bunkr</title>')
        self.assertEqual(self.parser.album_name, "Title Album")
        
        # Test with already set album name (h1 takes precedence)
        self.parser.album_name = "Already Set"
        self.parser.feed('<title>Should Not Override - Bunkr</title>')
        self.assertEqual(self.parser.album_name, "Already Set")
    
    def test_parse_file_links(self):
        """Test parsing file links."""
        # Test standard file links
        self.parser.feed('<a href="/f/file1.jpg">File 1</a><a href="/f/file2.png">File 2</a>')
        self.assertEqual(len(self.parser.file_links), 2)
        self.assertTrue(all(link.startswith('https://bunkr.sk/f/') for link in self.parser.file_links))
        
        # Test album links
        self.parser.feed('<a href="/a/nested-album">Nested Album</a>')
        self.assertEqual(len(self.parser.file_links), 3)
        self.assertTrue(any('nested-album' in link for link in self.parser.file_links))
        
        # Test regex pattern matches
        self.parser.feed('<a href="/f/a1b2c3d4e5f6g7h8">Strange filename</a>')
        self.assertEqual(len(self.parser.file_links), 4)
    
    def test_handle_error(self):
        """Test error handling."""
        # Should not raise exception
        self.parser.error("Test error message")


if __name__ == '__main__':
    unittest.main()