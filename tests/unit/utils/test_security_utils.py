"""
Unit tests for security utility functions.
"""
import unittest
from unittest import mock
import os
import base64
from bunkrd.utils.security_utils import (
    get_secret_key, 
    secure_xor_bytes, 
    decrypt_with_key,
    load_secret_from_env, 
    initialize_secret_key
)


class TestSecurityUtils(unittest.TestCase):
    """Test cases for security utility functions."""
    
    def test_get_secret_key(self):
        """Test generation of secret key from base and timestamp."""
        # Test that the same inputs produce the same key
        key1 = get_secret_key("test_key_base", 3600000)
        key2 = get_secret_key("test_key_base", 3600000)
        self.assertEqual(key1, key2)
        
        # Test that different timestamps produce different keys
        key3 = get_secret_key("test_key_base", 7200000)
        self.assertNotEqual(key1, key3)
        
        # Test that different bases produce different keys
        key4 = get_secret_key("different_key_base", 3600000)
        self.assertNotEqual(key1, key4)
    
    def test_secure_xor_bytes(self):
        """Test XOR operation between byte arrays."""
        # Test basic XOR operation
        data = b'test data'
        key = b'key'
        encrypted = secure_xor_bytes(data, key)
        
        # Verify the encrypted data is different from original
        self.assertNotEqual(data, encrypted)
        
        # Verify that applying XOR again decrypts back to original
        decrypted = secure_xor_bytes(encrypted.encode('utf-8'), key)
        self.assertEqual(data.decode('utf-8'), decrypted)
    
    def test_decrypt_with_key(self):
        """Test decryption of data using derived key."""
        # Create test data for encryption/decryption
        test_url = "https://example.com/test.jpg"
        test_key_base = "test_secret_key"
        test_timestamp = 3600000
        
        # Get the derived key
        key = get_secret_key(test_key_base, test_timestamp)
        
        # Manually encrypt the URL using XOR
        encrypted_bytes = secure_xor_bytes(test_url.encode('utf-8'), key)
        encrypted_b64 = base64.b64encode(encrypted_bytes.encode('utf-8')).decode('utf-8')
        
        # Test decryption function
        decrypted = decrypt_with_key(encrypted_b64, test_key_base, test_timestamp)
        self.assertEqual(decrypted, test_url)
        
        # Test with invalid base64
        with mock.patch('builtins.print'), mock.patch('logging.error'):
            result = decrypt_with_key("invalid-base64", test_key_base, test_timestamp)
            self.assertIsNone(result)
    
    def test_load_secret_from_env(self):
        """Test loading secrets from environment variables."""
        # Test with existing env var
        test_var_name = "TEST_SECRET_VAR"
        test_value = "test_secret_value"
        
        with mock.patch.dict(os.environ, {test_var_name: test_value}):
            loaded_value = load_secret_from_env(test_var_name)
            self.assertEqual(loaded_value, test_value)
        
        # Test with non-existent env var and default
        default_value = "default_value"
        loaded_value = load_secret_from_env("NON_EXISTENT_VAR", default_value)
        self.assertEqual(loaded_value, default_value)
        
        # Test with non-existent env var and no default
        with mock.patch('bunkrd.utils.security_utils.logger.warning') as mock_warning:
            loaded_value = load_secret_from_env("NON_EXISTENT_VAR")
            self.assertIsNone(loaded_value)
            mock_warning.assert_called_once()
    
    def test_initialize_secret_key_from_env(self):
        """Test initializing secret key from environment."""
        # Mock the environment variable
        with mock.patch('bunkrd.utils.security_utils.load_secret_from_env') as mock_load_secret:
            mock_load_secret.return_value = "secret_from_env"
            
            result = initialize_secret_key("TEST_KEY")
            self.assertEqual(result, "secret_from_env")
            mock_load_secret.assert_called_once_with("BUNKRDOWNLOADER_TEST_KEY")
    
    def test_initialize_secret_key_from_file(self):
        """Test initializing secret key from config file."""
        # Mock env var not found
        with mock.patch('bunkrd.utils.security_utils.load_secret_from_env') as mock_load_secret:
            mock_load_secret.return_value = None
            
            # Mock config file exists and contains key
            with mock.patch('bunkrd.utils.security_utils.Path') as mock_path:
                mock_config_file = mock.MagicMock()
                mock_path.home.return_value = mock.MagicMock()
                mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value = mock_config_file
                mock_config_file.exists.return_value = True
                
                # Mock file open and read
                mock_open = mock.mock_open(read_data="TEST_KEY=secret_from_file\nOTHER_KEY=othervalue")
                with mock.patch('builtins.open', mock_open):
                    result = initialize_secret_key("TEST_KEY")
                    self.assertEqual(result, "secret_from_file")
    
    def test_initialize_secret_key_not_found(self):
        """Test when secret key is not found anywhere."""
        # Mock env var not found
        with mock.patch('bunkrd.utils.security_utils.load_secret_from_env') as mock_load_secret:
            mock_load_secret.return_value = None
            
            # Mock config file doesn't exist
            with mock.patch('bunkrd.utils.security_utils.Path') as mock_path:
                mock_config_file = mock.MagicMock()
                mock_path.home.return_value = mock.MagicMock()
                mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value = mock_config_file
                mock_config_file.exists.return_value = False
                
                result = initialize_secret_key("TEST_KEY")
                self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()