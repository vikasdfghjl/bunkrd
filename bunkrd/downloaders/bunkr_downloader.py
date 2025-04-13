"""
Bunkr downloader implementation.
"""
import re
import json
import logging
import requests
from math import floor
from base64 import b64decode
import os

from .base_downloader import BaseDownloader
from ..config import BUNKR_VS_API_URL, SECRET_KEY_BASE
from ..utils.security_utils import decrypt_with_key

# Setup logging
logger = logging.getLogger(__name__)

class BunkrDownloader(BaseDownloader):
    """
    Class for downloading content from Bunkr.
    
    This class provides specific functionality for handling Bunkr URLs,
    including decryption of the download links.
    """
    
    def get_real_download_url(self, url):
        """
        Get the real download URL from a Bunkr file URL.
        
        Args:
            url (str): The Bunkr URL to get the real download link from
            
        Returns:
            dict: Dictionary with the download URL and size, or None if failed
        """
        try:
            # Ensure URL has https scheme
            url = url if 'https' in url else f'https://bunkr.sk{url}'
            logger.debug(f"Processing Bunkr URL: {url}")
            
            # Find the slug from the URL using regex
            match = re.search(r'\/f\/(.*?)$', url)
            if not match:
                logger.error(f"Could not extract slug from URL {url}")
                print(f"\t[-] Error: Could not extract slug from URL {url}")
                return None
                
            slug = match.group(1)
            logger.debug(f"Extracted slug: {slug}")
            
            encryption_data = self._get_encryption_data(slug)
            
            if not encryption_data:
                logger.error(f"Could not get encryption data for slug {slug}")
                print(f"\t[-] Error: Could not get encryption data for slug {slug}")
                return None
            
            # Log the encryption data structure (safely)
            logger.debug(f"Encryption data keys: {list(encryption_data.keys())}")
            if 'timestamp' in encryption_data:
                logger.debug(f"Timestamp from API: {encryption_data['timestamp']}")
            if 'url' in encryption_data:
                url_data = encryption_data['url']
                logger.debug(f"Encrypted URL length: {len(url_data) if url_data else 'None'}")
                logger.debug(f"URL data first 30 chars: {url_data[:30] if url_data else 'None'}")
                
            # TEMPORARY: Dump raw encryption data to a file for analysis
            self._dump_debug_info(slug, encryption_data)
            
            # Try the new direct URL method if URL field is available
            if 'url' in encryption_data and encryption_data['url'].startswith('http'):
                logger.info(f"Using direct URL from API response for slug {slug}")
                return {'url': encryption_data['url'], 'size': -1}
                
            decrypted_url = self._decrypt_encrypted_url(encryption_data)
            if not decrypted_url:
                logger.error(f"Could not decrypt URL for slug {slug}")
                print(f"\t[-] Error: Could not decrypt URL for slug {slug}")
                return None
                
            logger.debug(f"Successfully decrypted download URL: {decrypted_url[:30]}...")
            return {'url': decrypted_url, 'size': -1}
        except Exception as e:
            logger.exception(f"Error getting real download URL: {str(e)}")
            print(f"\t[-] Error getting real download URL: {str(e)}")
            return None
    
    def _dump_debug_info(self, slug, data):
        """
        Dump API response data to a file for debugging purposes
        
        Args:
            slug (str): The file slug
            data (dict): The data to dump
        """
        try:
            debug_dir = os.path.join(os.getcwd(), 'debug_logs')
            os.makedirs(debug_dir, exist_ok=True)
            
            debug_file = os.path.join(debug_dir, f'api_response_{slug}.json')
            print(f"Dumping API response data to {debug_file} for analysis")
            
            with open(debug_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to dump debug info: {str(e)}")
    
    def _get_encryption_data(self, slug):
        """
        Get encryption data for a Bunkr slug.
        
        Args:
            slug (str): The Bunkr slug
            
        Returns:
            dict: The encryption data from the API, or None if failed
        """
        try:
            # Debug the API URL and request payload
            logger.debug(f"Making API request to: {BUNKR_VS_API_URL}")
            logger.debug(f"Request payload: {{'slug': '{slug}'}}")
            
            # Using the new rate-limited API request method with robots.txt check 
            # and randomized user-agent rotation
            r = self.make_api_request('post', BUNKR_VS_API_URL, json={'slug': slug})
            
            logger.debug(f"API response status code: {r.status_code}")
            logger.debug(f"API response headers: {dict(r.headers)}")
            
            if r.status_code in (200, 201, 204):
                try:
                    # Log the raw response content first (limited length)
                    raw_content = r._content
                    logger.debug(f"Raw API response first 100 bytes: {raw_content[:100].hex() if raw_content else 'None'}")
                    
                    # Parse the JSON response
                    data = json.loads(r._content)
                    logger.debug(f"Successfully parsed JSON response with keys: {list(data.keys())}")
                    
                    # Print the full API response for analysis
                    print(f"\t[DEBUG] API Response Keys: {list(data.keys())}")
                    
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {str(e)}")
                    logger.debug(f"Failed JSON content (first 100 chars): {r._content[:100] if r._content else 'None'}")
                    return None
            else:
                logger.error(f"HTTP ERROR {r.status_code} getting encryption data for slug {slug}")
                logger.debug(f"Error response content: {r.text[:200] if r.text else 'None'}")
                print(f"\t\t[-] HTTP ERROR {r.status_code} getting encryption data")
                return None
        except (json.JSONDecodeError, requests.RequestException) as e:
            logger.error(f"Error getting encryption data: {str(e)}")
            print(f"\t\t[-] Error getting encryption data: {str(e)}")
            return None

    def _decrypt_encrypted_url(self, encryption_data):
        """
        Decrypt an encrypted Bunkr URL.
        
        Args:
            encryption_data (dict): The encryption data from the API
            
        Returns:
            str: The decrypted URL, or None if decryption failed
        """
        try:
            logger.debug(f"Attempting to decrypt URL using encryption data")
            
            if not encryption_data:
                logger.error("Encryption data is None")
                return None
                
            # Debug the encryption data
            required_fields = ['timestamp', 'url']
            missing_fields = [field for field in required_fields if field not in encryption_data]
            
            if missing_fields:
                logger.error(f"Missing required encryption fields: {missing_fields}")
                logger.debug(f"Available fields: {list(encryption_data.keys())}")
                print(f"\t\t[-] Error: Missing required encryption data fields: {missing_fields}")
                return None
                
            # Log the key information we'll use for decryption
            logger.debug(f"Using timestamp for decryption: {encryption_data['timestamp']}")
            logger.debug(f"SECRET_KEY_BASE is {'available' if SECRET_KEY_BASE else 'missing'}")
            logger.debug(f"SECRET_KEY_BASE first 3 chars: {SECRET_KEY_BASE[:3] + '...' if SECRET_KEY_BASE else 'None'}")
            
            # Use the secure decryption method
            decrypted_url = decrypt_with_key(
                encryption_data['url'],
                SECRET_KEY_BASE,
                encryption_data['timestamp']
            )
            
            # Basic validation that we got a proper URL
            if not decrypted_url:
                logger.error("Decryption returned None")
                return None
                
            if not decrypted_url.startswith('http'):
                logger.warning(f"Decrypted URL doesn't look valid: {decrypted_url[:30]}...")
                print(f"\t\t[-] Warning: Decrypted URL doesn't look valid: {decrypted_url[:30]}...")
                
            return decrypted_url
                
        except Exception as e:
            logger.exception(f"Unexpected error in decrypt_encrypted_url: {str(e)}")
            print(f"\t\t[-] Unexpected error in decrypt_encrypted_url: {str(e)}")
            return None