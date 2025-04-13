"""
Parser for Cyberdrop album pages.
"""
import re
import requests
from bs4 import BeautifulSoup
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
    
    def parse_album(self, url):
        """
        Parse a Cyberdrop album page and extract file information.
        
        Args:
            url (str): The URL of the Cyberdrop album
            
        Returns:
            dict: Dictionary containing album name and list of file URLs
        """
        try:
            # Add proper scheme if missing
            if not url.startswith('http'):
                url = f'https://{url}'
            
            # Check robots.txt if enabled
            if RESPECT_ROBOTS_TXT and not can_fetch(url, self.session.headers.get('User-Agent')):
                print(f"[-] Access to {url} is denied by robots.txt")
                return {"album_name": ERROR_MESSAGES["robots_txt_denied"], "files": []}
            
            # Make request with rate limiting, UA rotation, etc.
            response = make_request_with_rate_limit(
                self.session, 
                'get', 
                url, 
                timeout=15, 
                check_robots=False  # Already checked above
            )
                
            if response.status_code != 200:
                print(f"[-] HTTP error: {response.status_code} for URL: {url}")
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
                print(f"[-] No downloadable items found in album: {url}")
                
            return {"album_name": album_name, "files": file_links}
        except Exception as e:
            print(f"[-] Error parsing Cyberdrop album {url}: {str(e)}")
            return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}