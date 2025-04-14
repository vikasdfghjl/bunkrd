"""
Parser for Bunkr album pages.
"""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
from ..config import (
    REQUEST_HEADERS, ERROR_MESSAGES,
    USE_PROXY, DEFAULT_PROXY,
    RESPECT_ROBOTS_TXT
)
from ..utils.file_utils import remove_illegal_chars
from ..utils.request_utils import (
    create_session_with_random_ua, add_proxy_to_session,
    make_request_with_rate_limit, can_fetch
)

# Setup logging
logger = logging.getLogger(__name__)

class BunkrParser:
    """
    Class for parsing Bunkr album pages and extracting file information.
    """
    
    def __init__(self, session=None, proxy_url=None):
        """
        Initialize the Bunkr parser.
        
        Args:
            session (requests.Session, optional): A requests session to use.
                If None, a new session will be created.
            proxy_url (str, optional): A proxy URL to use. If None and USE_PROXY is True,
                DEFAULT_PROXY will be used.
        """
        self.proxy_url = proxy_url if proxy_url is not None else (DEFAULT_PROXY if USE_PROXY else None)
        self.session = session or self.create_session()
    
    def create_session(self):
        """
        Create a new requests session with appropriate headers and proxy settings.
        
        Returns:
            requests.Session: A new session with random user agent and proxy if configured
        """
        session = create_session_with_random_ua()
        if self.proxy_url:
            session = add_proxy_to_session(session, self.proxy_url)
        return session
    
    def parse_album(self, url):
        """
        Parse a Bunkr album page and extract file information.
        
        This method implements a robust web scraping approach with multiple extraction
        strategies and fallback mechanisms to handle different site layouts and
        potential page structure changes over time.
        
        Args:
            url (str): The URL of the Bunkr album
            
        Returns:
            dict: Dictionary containing:
                - album_name (str): Name of the album extracted from the page
                - files (list): List of file URLs found in the album
        """
        try:
            # Add proper scheme if missing (normalize URL format)
            if not url.startswith('http'):
                url = f'https://{url}'
                
            # Standardize Bunkr URLs - the site uses multiple domains that point to same content
            # Converting all to bunkr.sk for consistency
            original_url = url
            url = url.replace('bunkr.la', 'bunkr.sk').replace('bunkr.is', 'bunkr.sk').replace('bunkr.cr', 'bunkr.sk')
            
            logger.info(f"Parsing album at URL: {url} (original: {original_url})")
            
            # Check robots.txt if enabled in config - respect site's crawling policies
            if RESPECT_ROBOTS_TXT and not can_fetch(url, self.session.headers.get('User-Agent')):
                logger.warning(f"Access to {url} is denied by robots.txt")
                return {"album_name": ERROR_MESSAGES["robots_txt_denied"], "files": []}
            
            # Make request with rate limiting, UA rotation, etc. to avoid detection and IP bans
            response = make_request_with_rate_limit(
                self.session, 
                'get', 
                url, 
                timeout=15, 
                check_robots=False  # Already checked above
            )
            
            # Handle HTTP errors (404, 403, etc.)
            if response.status_code != 200:
                logger.error(f"HTTP error: {response.status_code} for URL: {url}")
                return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
            
            logger.info(f"Successfully fetched URL: {url}")
            
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # PART 1: Extract album name from page heading
            # First try to find h1 with specific class, then fallback to any h1
            h1_tag = soup.find('h1', class_='block truncate')
            if not h1_tag:
                h1_tag = soup.find('h1')  # Try without class if not found
                
            album_name = "unknown_album"
            if h1_tag:
                album_name = remove_illegal_chars(h1_tag.text.strip())
                logger.info(f"Found album name: {album_name}")
            
            # PART 2: Extract file links using multiple strategies
            file_links = []
            
            # Strategy 1: Look for links with 'shadow-md' class (primary approach)
            # This targets the standard thumbnail container links in most Bunkr layouts
            links = soup.find_all('a', class_=lambda c: c and 'shadow-md' in c)
            for link in links:
                href = link.get('href')
                if href and ('/f/' in href or '/a/' in href or '/d/' in href):
                    file_links.append(urljoin('https://bunkr.sk', href))
            
            # Strategy 2: Look for any links with paths matching file/album patterns
            # Fallback if the page layout changed and class-based approach fails
            if not file_links:
                logger.info("No links found with shadow-md class, trying alternative methods")
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and ('/f/' in href or '/a/' in href or '/d/' in href):
                        file_links.append(urljoin('https://bunkr.sk', href))
            
            # Strategy 3: Use regex pattern matching as a last resort
            # This is the most permissive approach but might catch false positives
            if not file_links:
                logger.info("No links found with image elements, trying regex pattern matching")
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href')
                    if href and re.search(r'/(f|a|d)/[a-zA-Z0-9]{8,}', href):
                        file_links.append(urljoin('https://bunkr.sk', href))
            
            # Log detailed debug info if no files were found despite all strategies
            # This helps diagnose site changes that break the parser
            if not file_links:
                logger.warning(f"No downloadable items found in album: {url}")
                # Comment out debug info section - for debugging purposes only
                '''
                # Print some debug info about page structure to help diagnose issues
                all_links = soup.find_all('a', href=True)
                logger.debug(f"Found {len(all_links)} total links in the page")
                for i, link in enumerate(all_links[:10]):  # First 10 links only
                    logger.debug(f"Link {i}: {link.get('href')} - Classes: {link.get('class')} - Text: {link.text.strip()[:30]}")
                '''
            else:
                logger.info(f"Found {len(file_links)} files in album")
                
            return {"album_name": album_name, "files": file_links}
        except Exception as e:
            # Catch and log any unexpected exceptions to prevent crash
            logger.exception(f"Error parsing Bunkr album {url}: {str(e)}")
            return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}