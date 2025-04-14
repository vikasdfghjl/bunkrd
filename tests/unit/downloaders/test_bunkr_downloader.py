"""
Unit tests for BunkrDownloader implementation.
"""
import unittest
from unittest import mock
import json
import os
import tempfile
import shutil
from bunkrd.downloaders.bunkr_downloader import BunkrDownloader
from tests.mock_services import MockResponse


class TestBunkrDownloader(unittest.TestCase):
    """Test cases for BunkrDownloader class."""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.temp_dir = tempfile.mkdtemp()
        # Create mock session
        self.mock_session = mock.Mock()
        self.mock_session.headers = {'User-Agent': 'test-agent'}
        # Initialize downloader with mock session
        self.downloader = BunkrDownloader(session=self.mock_session)
        
    def tearDown(self):
        """Clean up after each test."""
        shutil.rmtree(self.temp_dir)
    
    def test_init(self):
        """Test initialization of BunkrDownloader."""
        self.assertEqual(self.downloader.session, self.mock_session)
        self.assertIsNone(self.downloader.proxy_url)
    
    def test_get_real_download_url_success(self):
        """Test successful retrieval of download URL."""
        # Setup mock for API request
        mock_api_response = MockResponse(
            status_code=200,
            content=json.dumps({
                'url': 'encrypted-url',
                'timestamp': 1649776000
            }).encode('utf-8')
        )
        self.downloader.make_api_request = mock.Mock(return_value=mock_api_response)
        
        # Mock the decryption function
        with mock.patch(
            'bunkrd.downloaders.bunkr_downloader.decrypt_with_key',
            return_value='https://example.com/decrypted-url'
        ) as mock_decrypt:
            result = self.downloader.get_real_download_url('https://bunkr.sk/f/test-file')
            
            # Assertions
            self.assertIsNotNone(result)
            self.assertEqual(result['url'], 'https://example.com/decrypted-url')
            mock_decrypt.assert_called_once()
    
    def test_get_real_download_url_with_relative_path(self):
        """Test URL retrieval with relative path."""
        # Setup mock for API request
        mock_api_response = MockResponse(
            status_code=200,
            content=json.dumps({
                'url': 'encrypted-url',
                'timestamp': 1649776000
            }).encode('utf-8')
        )
        self.downloader.make_api_request = mock.Mock(return_value=mock_api_response)
        
        # Mock the decryption function
        with mock.patch(
            'bunkrd.downloaders.bunkr_downloader.decrypt_with_key',
            return_value='https://example.com/decrypted-url'
        ) as mock_decrypt:
            result = self.downloader.get_real_download_url('/f/test-file')
            
            # Assertions
            self.assertIsNotNone(result)
            self.assertEqual(result['url'], 'https://example.com/decrypted-url')
    
    def test_get_real_download_url_api_error(self):
        """Test URL retrieval with API error."""
        # Setup mock for API request with error
        mock_api_response = MockResponse(status_code=404)
        self.downloader.make_api_request = mock.Mock(return_value=mock_api_response)
        
        with mock.patch('builtins.print') as mock_print:
            result = self.downloader.get_real_download_url('https://bunkr.sk/f/test-file')
            
            # Assertions
            self.assertIsNone(result)
            mock_print.assert_called()
    
    def test_get_real_download_url_invalid_url(self):
        """Test URL retrieval with invalid URL format."""
        with mock.patch('builtins.print') as mock_print:
            result = self.downloader.get_real_download_url('https://bunkr.sk/invalid-url')
            
            # Assertions
            self.assertIsNone(result)
            mock_print.assert_called()
    
    def test_get_encryption_data_success(self):
        """Test successful retrieval of encryption data."""
        # Setup mock for API request
        mock_api_response = MockResponse(
            status_code=200,
            content=json.dumps({
                'url': 'encrypted-url',
                'timestamp': 1649776000
            }).encode('utf-8')
        )
        self.downloader.make_api_request = mock.Mock(return_value=mock_api_response)
        
        result = self.downloader._get_encryption_data('test-slug')
        
        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result['url'], 'encrypted-url')
        self.assertEqual(result['timestamp'], 1649776000)
        self.downloader.make_api_request.assert_called_once()
    
    def test_decrypt_encrypted_url_success(self):
        """Test successful decryption of URL."""
        encryption_data = {
            'url': 'encrypted-url',
            'timestamp': 1649776000
        }
        
        with mock.patch(
            'bunkrd.downloaders.bunkr_downloader.decrypt_with_key',
            return_value='https://example.com/decrypted-url'
        ) as mock_decrypt:
            result = self.downloader._decrypt_encrypted_url(encryption_data)
            
            # Assertions
            self.assertEqual(result, 'https://example.com/decrypted-url')
            mock_decrypt.assert_called_once_with(
                'encrypted-url', 
                mock.ANY,  # SECRET_KEY_BASE
                1649776000
            )
    
    def test_decrypt_encrypted_url_missing_data(self):
        """Test URL decryption with missing data."""
        # Test with missing url
        with mock.patch('builtins.print') as mock_print:
            result = self.downloader._decrypt_encrypted_url({
                'timestamp': 1649776000
            })
            
            # Assertions
            self.assertIsNone(result)
            mock_print.assert_called()
        
        # Test with missing timestamp
        with mock.patch('builtins.print') as mock_print:
            result = self.downloader._decrypt_encrypted_url({
                'url': 'encrypted-url'
            })
            
            # Assertions
            self.assertIsNone(result)
            mock_print.assert_called()
    
    def test_decrypt_encrypted_url_decrypt_error(self):
        """Test URL decryption with decryption error."""
        encryption_data = {
            'url': 'encrypted-url',
            'timestamp': 1649776000
        }
        
        with mock.patch(
            'bunkrd.downloaders.bunkr_downloader.decrypt_with_key',
            return_value=None  # Simulates decryption failure
        ) as mock_decrypt:
            with mock.patch('builtins.print') as mock_print:
                with mock.patch('bunkrd.downloaders.bunkr_downloader.logger.error') as mock_logger_error:
                    result = self.downloader._decrypt_encrypted_url(encryption_data)
                    
                    # Assertions
                    self.assertIsNone(result)
                    # Check that either print or logging was used for error reporting
                    self.assertTrue(
                        mock_print.called or mock_logger_error.called,
                        "Neither print nor logger.error was called"
                    )


if __name__ == '__main__':
    unittest.main()