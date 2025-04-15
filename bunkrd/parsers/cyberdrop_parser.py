"""
Parser for Cyberdrop album pages.
"""
import re
import requests
import logging
from bs4 import BeautifulSoup
from html.parser import HTMLParser
from urllib.parse import urljoin
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

class CyberdropParser:
    """
    Class for parsing Cyberdrop album pages and extracting file information.
    """
    
    def __init__(self, session=None, proxy_url=None):
        """
        Initialize the Cyberdrop parser.
        
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
    
    def parse_album(self, url, use_incremental=True):
        """
        Parse a Cyberdrop album page and extract file information.
        
        Args:
            url (str): The URL of the Cyberdrop album
            use_incremental (bool, optional): Whether to use incremental parsing for large pages
            
        Returns:
            dict: Dictionary containing album name and list of file URLs
        """
        try:
            # Add proper scheme if missing
            if not url.startswith('http'):
                url = f'https://{url}'
            
            # Check robots.txt if enabled
            if RESPECT_ROBOTS_TXT and not can_fetch(url, self.session.headers.get('User-Agent')):
                logger.warning(f"Access to {url} is denied by robots.txt")
                return {"album_name": ERROR_MESSAGES["robots_txt_denied"], "files": []}
            
            if use_incremental:
                return self._parse_album_incremental(url)
            else:
                return self._parse_album_traditional(url)
                
        except Exception as e:
            logger.exception(f"Error parsing Cyberdrop album {url}: {str(e)}")
            return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
            
    def _parse_album_traditional(self, url):
        """
        Parse album using traditional BeautifulSoup method (loads entire HTML into memory).
        
        Args:
            url (str): The URL of the Cyberdrop album
            
        Returns:
            dict: Dictionary containing album_name and files
        """
        try:
            # Make request with rate limiting, UA rotation, etc.
            response = make_request_with_rate_limit(
                self.session, 
                'get', 
                url, 
                timeout=15, 
                check_robots=False  # Already checked in parse_album
            )
                
            if response.status_code != 200:
                logger.error(f"HTTP error: {response.status_code} for URL: {url}")
                return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract album name
            album_name = ERROR_MESSAGES["unknown_album"]
            title_el = soup.find('title')
            
            if title_el:
                album_name = title_el.text.strip()
                # Remove "Cyberdrop.me - " prefix if present
                album_name = re.sub(r'^Cyberdrop\.me\s*-\s*', '', album_name)
                album_name = remove_illegal_chars(album_name)
                
            # Extract file links
            file_links = []
            links = soup.select('a.image')
            
            for link in links:
                href = link.get('href')
                if href:
                    file_links.append(href)
                    
            if not file_links:
                logger.warning(f"No downloadable items found in album: {url}")
                
            logger.info(f"Found {len(file_links)} files in album using traditional parser")
            return {"album_name": album_name, "files": file_links}
            
        except Exception as e:
            logger.exception(f"Error in traditional parsing for {url}: {str(e)}")
            return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
    
    def _parse_album_incremental(self, url):
        """
        Parse album using incremental HTML parsing to reduce memory usage.
        Perfect for extremely large album pages.
        
        Args:
            url (str): The URL of the Cyberdrop album
            
        Returns:
            dict: Dictionary containing album_name and files
        """
        logger.info(f"Using incremental HTML parser for: {url}")
        
        # Create an incremental HTML parser to process the content in chunks
        incremental_parser = CyberdropIncrementalParser(base_url=url)
        
        try:
            # Stream the response to process it incrementally
            response = self.session.get(url, stream=True, timeout=30)
            
            # Handle HTTP errors (404, 403, etc.)
            if response.status_code != 200:
                logger.error(f"HTTP error: {response.status_code} for URL: {url}")
                return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
            
            # Process the HTML content in chunks to reduce memory usage
            chunk_size = 8192  # 8KB chunks
            for chunk in response.iter_content(chunk_size=chunk_size, decode_unicode=True):
                if chunk:  # Filter out keep-alive chunks
                    incremental_parser.feed(chunk)
                    
                    # Periodically log progress for large albums
                    if len(incremental_parser.file_links) > 0 and len(incremental_parser.file_links) % 50 == 0:
                        logger.debug(f"Incremental parser: found {len(incremental_parser.file_links)} files so far")
            
            # Clean up the parser once we're done
            incremental_parser.close()
            
            album_name = incremental_parser.album_name
            if not album_name or album_name.strip() == "":
                album_name = "unknown_album"
            else:
                # Remove "Cyberdrop.me - " prefix if present
                album_name = re.sub(r'^Cyberdrop\.me\s*-\s*', '', album_name)
                album_name = remove_illegal_chars(album_name)
            
            file_links = incremental_parser.file_links
            logger.info(f"Incremental parser completed: found {len(file_links)} files in album")
            
            return {"album_name": album_name, "files": file_links}
            
        except Exception as e:
            logger.exception(f"Error in incremental parsing for {url}: {str(e)}")
            # Return whatever we've managed to parse so far, if anything
            album_name = incremental_parser.album_name or "unknown_album"
            # Remove "Cyberdrop.me - " prefix if present
            album_name = re.sub(r'^Cyberdrop\.me\s*-\s*', '', album_name)
            album_name = remove_illegal_chars(album_name)
            return {
                "album_name": album_name, 
                "files": incremental_parser.file_links
            }


class CyberdropIncrementalParser(HTMLParser):
    """
    Custom incremental HTML parser for Cyberdrop albums.
    Processes HTML in chunks to minimize memory usage.
    """
    
    def __init__(self, base_url=None):
        """
        Initialize the incremental parser.
        
        Args:
            base_url (str, optional): Base URL to use for resolving relative links
        """
        super().__init__(convert_charrefs=True)
        self.base_url = base_url or ''
        self.in_title = False
        self.title_text = ""
        self.album_name = None
        self.file_links = []
        self.in_a_tag = False
        self.current_a_class = None
        self.current_href = None
    
    def handle_starttag(self, tag, attrs):
        """Process the opening tag and its attributes."""
        attrs_dict = dict(attrs)
        
        if tag == 'title':
            self.in_title = True
            self.title_text = ""
            return
            
        # Track anchor tags for potential file links
        if tag == 'a':
            self.in_a_tag = True
            self.current_href = attrs_dict.get('href')
            self.current_a_class = attrs_dict.get('class', '')
            
            # Check if this is an image link (specific to Cyberdrop)
            if self.current_href and 'image' in self.current_a_class:
                # Found an image link - add to our collection
                full_url = urljoin(self.base_url, self.current_href)
                if full_url not in self.file_links:
                    self.file_links.append(full_url)
    
    def handle_endtag(self, tag):
        """Process the closing tag."""
        if tag == 'title':
            self.in_title = False
            # If we found title text, use it as album name
            if self.title_text:
                self.album_name = self.title_text.strip()
        elif tag == 'a':
            self.in_a_tag = False
            self.current_href = None
            self.current_a_class = None
    
    def handle_data(self, data):
        """Process the text content."""
        # Capture title text
        if self.in_title:
            self.title_text += data
    
    def error(self, message):
        """Handle parsing errors gracefully."""
        logger.warning(f"HTML parser error: {message}")