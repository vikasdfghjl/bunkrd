"""
Parser for Bunkr album pages.
"""
import re
import requests
from bs4 import BeautifulSoup
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import logging
from ..config import (
    REQUEST_HEADERS, ERROR_MESSAGES,
    USE_PROXY, DEFAULT_PROXY,
    RESPECT_ROBOTS_TXT
)
from ..utils.file_utils import remove_illegal_chars
from ..utils.request_utils import (
    make_request_with_rate_limit, can_fetch
)
from ..utils.session_factory import SessionFactory

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
        return SessionFactory.create_session(self.proxy_url)
    
    def parse_album(self, url, use_incremental=True):
        """
        Parse a Bunkr album page and extract file information.
        
        This method implements a robust web scraping approach with multiple extraction
        strategies and fallback mechanisms to handle different site layouts and
        potential page structure changes over time.
        
        Args:
            url (str): The URL of the Bunkr album
            use_incremental (bool, optional): Whether to use incremental parsing for large pages
            
        Returns:
            dict: Dictionary containing:
                - album_name (str): Name of the album extracted from the page
                - files (list): List of file URLs found in the album
        """
        try:
            # Store original URL for potential album name extraction
            original_url = url
            
            # Add proper scheme if missing (normalize URL format)
            if not url.startswith('http'):
                url = f'https://{url}'
                
            # Standardize Bunkr URLs - the site uses multiple domains that point to same content
            # Converting all to bunkr.sk for consistency
            url = url.replace('bunkr.la', 'bunkr.sk').replace('bunkr.is', 'bunkr.sk').replace('bunkr.cr', 'bunkr.sk')
            
            logger.info(f"Parsing album at URL: {url} (original: {original_url})")
            
            # Check robots.txt if enabled in config - respect site's crawling policies
            if RESPECT_ROBOTS_TXT and not can_fetch(url, self.session.headers.get('User-Agent')):
                logger.warning(f"Access to {url} is denied by robots.txt")
                # Extract album name from URL for robots.txt denied case
                album_name = self._extract_album_id_from_url(original_url) or ERROR_MESSAGES["robots_txt_denied"]
                return {"album_name": album_name, "files": []}
            
            # Parse album with selected method
            if use_incremental:
                result = self._parse_album_incremental(url)
            else:
                result = self._parse_album_traditional(url)
                
            # If no album name was found, try to extract from the URL as a fallback
            if result["album_name"] == "unknown_album" or ERROR_MESSAGES["unknown_album"] in result["album_name"]:
                album_id = self._extract_album_id_from_url(original_url)
                if album_id:
                    result["album_name"] = album_id
                    
            return result
        except Exception as e:
            # Catch and log any unexpected exceptions to prevent crash
            logger.exception(f"Error parsing Bunkr album {url}: {str(e)}")
            # Try to extract album name from URL as last resort
            album_name = self._extract_album_id_from_url(url) or ERROR_MESSAGES["unknown_album"]
            return {"album_name": album_name, "files": []}
            
    def _parse_album_traditional(self, url):
        """
        Parse album using traditional BeautifulSoup method (loads entire HTML into memory).
        
        Args:
            url (str): The URL of the Bunkr album
            
        Returns:
            dict: Dictionary containing album_name and files
        """
        try:
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
            
            # Debug the HTML content to see what's available
            self._debug_html_content(url, response.text)
            
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # PART 1: Extract album name using multiple strategies
            album_name = "unknown_album"
            
            # Strategy 1: Find h1 with specific class (original approach)
            h1_tag = soup.find('h1', class_='block truncate')
            if h1_tag and h1_tag.text.strip():
                album_name = remove_illegal_chars(h1_tag.text.strip())
                logger.info(f"Found album name from h1.block.truncate: {album_name}")
            
            # Strategy 2: Any h1 tag
            if album_name == "unknown_album":
                h1_tag = soup.find('h1')
                if h1_tag and h1_tag.text.strip():
                    album_name = remove_illegal_chars(h1_tag.text.strip())
                    logger.info(f"Found album name from h1: {album_name}")
            
            # Strategy 3: Extract from page title (format: "Album Name - Bunkr")
            if album_name == "unknown_album":
                title_tag = soup.find('title')
                if title_tag and title_tag.text:
                    title_text = title_tag.text.strip()
                    # Check for common title patterns
                    if ' - ' in title_text:
                        title_parts = title_text.split(' - ')
                        if len(title_parts) > 1 and title_parts[0].strip():
                            album_name = remove_illegal_chars(title_parts[0].strip())
                            logger.info(f"Found album name from page title: {album_name}")
            
            # Strategy 4: Look for meta tags with album name
            if album_name == "unknown_album":
                meta_tag = soup.find('meta', property='og:title') or soup.find('meta', name='title')
                if meta_tag and meta_tag.get('content'):
                    meta_content = meta_tag.get('content').strip()
                    if ' - ' in meta_content:
                        meta_parts = meta_content.split(' - ')
                        album_name = remove_illegal_chars(meta_parts[0].strip())
                    else:
                        album_name = remove_illegal_chars(meta_content)
                    logger.info(f"Found album name from meta tag: {album_name}")
            
            # Strategy 5: Find header elements with album name
            if album_name == "unknown_album":
                for header_tag in ['h2', 'h3', 'div']:
                    header = soup.find(header_tag, class_=lambda c: c and ('title' in c.lower() or 'header' in c.lower() or 'heading' in c.lower()))
                    if header and header.text.strip():
                        album_name = remove_illegal_chars(header.text.strip())
                        logger.info(f"Found album name from {header_tag} with title/header class: {album_name}")
                        break
            
            # Strategy 6: For bunkr.cr, check the breadcrumbs or navbar for album name
            if album_name == "unknown_album":
                if 'bunkr.cr' in url:
                    # Try breadcrumb navigation
                    breadcrumb = soup.find(['nav', 'ol'], class_=lambda c: c and ('breadcrumb' in c.lower() or 'navigation' in c.lower()))
                    if breadcrumb:
                        # Look for the last item which is often the current page
                        items = breadcrumb.find_all('li')
                        if items and len(items) > 1:  # At least 2 items (home + album)
                            last_item = items[-1]
                            if last_item.text.strip():
                                album_name = remove_illegal_chars(last_item.text.strip())
                                logger.info(f"Found album name from breadcrumb: {album_name}")
            
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
            if not file_links:
                logger.warning(f"No downloadable items found in album: {url}")
            else:
                logger.info(f"Found {len(file_links)} files in album")
                
            return {"album_name": album_name, "files": file_links}
        except Exception as e:
            # Catch and log any unexpected exceptions to prevent crash
            logger.exception(f"Error in traditional parsing for {url}: {str(e)}")
            return {"album_name": ERROR_MESSAGES["unknown_album"], "files": []}
    
    def _parse_album_incremental(self, url):
        """
        Parse album using incremental HTML parsing to reduce memory usage.
        Perfect for extremely large album pages.
        
        Args:
            url (str): The URL of the Bunkr album
            
        Returns:
            dict: Dictionary containing album_name and files
        """
        logger.info(f"Using incremental HTML parser for: {url}")
        
        # Create an incremental HTML parser to process the content in chunks
        incremental_parser = BunkrIncrementalParser(base_url='https://bunkr.sk')
        
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
                album_name = remove_illegal_chars(album_name)
            
            file_links = incremental_parser.file_links
            
            # Apply regex-based filtering as a final step for quality control
            filtered_links = []
            for link in file_links:
                if '/f/' in link or '/a/' in link or '/d/' in link:
                    filtered_links.append(link)
                elif re.search(r'/(f|a|d)/[a-zA-Z0-9]{8,}', link):
                    filtered_links.append(link)
            
            logger.info(f"Incremental parser completed: found {len(filtered_links)} files in album")
            return {"album_name": album_name, "files": filtered_links}
            
        except Exception as e:
            logger.exception(f"Error in incremental parsing for {url}: {str(e)}")
            # Return whatever we've managed to parse so far, if anything
            album_name = incremental_parser.album_name or "unknown_album"
            album_name = remove_illegal_chars(album_name)
            return {
                "album_name": album_name, 
                "files": incremental_parser.file_links
            }

    def _extract_album_id_from_url(self, url):
        """
        Extract album ID from URL to use as a fallback album name.
        
        Args:
            url (str): The URL of the Bunkr album
            
        Returns:
            str: Album ID extracted from URL path, or None if not found
        """
        try:
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            # Check if the URL matches the expected album pattern
            if len(path_parts) >= 2 and path_parts[0] == 'a':
                album_id = path_parts[1]
                # Make sure it's a valid album ID (alphanumeric, reasonable length)
                if album_id and len(album_id) >= 3:
                    logger.info(f"Extracted album ID from URL: {album_id}")
                    return f"bunkr_album_{album_id}"
        except Exception as e:
            logger.warning(f"Failed to extract album ID from URL: {url} - {str(e)}")
        
        return None

    def _debug_html_content(self, url, response_text, save_to_file=True):
        """
        Debug helper to log HTML content and save to file for inspection.
        
        Args:
            url (str): URL being parsed
            response_text (str): HTML content from response
            save_to_file (bool): Whether to save content to a debug file
        """
        # Limit content for logging to avoid overwhelming logs
        content_preview = response_text[:500] + '...' if len(response_text) > 500 else response_text
        logger.debug(f"HTML content preview for {url}: {content_preview}")
        
        if save_to_file:
            import os
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'debug_logs')
            os.makedirs(debug_dir, exist_ok=True)
            
            # Create a readable filename from URL
            url_parts = urlparse(url)
            file_name = f"html_debug_{url_parts.netloc.replace('.', '_')}_{url_parts.path.replace('/', '_')}.html"
            file_path = os.path.join(debug_dir, file_name)
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"<!-- Debug HTML for URL: {url} -->\n")
                    f.write(response_text)
                logger.info(f"Saved HTML debug content to {file_path}")
            except Exception as e:
                logger.warning(f"Failed to save HTML debug content: {str(e)}")


class BunkrIncrementalParser(HTMLParser):
    """
    Custom incremental HTML parser for Bunkr albums.
    Processes HTML in chunks to minimize memory usage.
    """
    
    def __init__(self, base_url=None):
        """
        Initialize the incremental parser.
        
        Args:
            base_url (str, optional): Base URL to use for resolving relative links
        """
        super().__init__(convert_charrefs=True)
        self.base_url = base_url or 'https://bunkr.sk'
        # Album name extraction
        self.in_h1 = False
        self.h1_class = None
        self.album_name = None
        self.in_title = False
        self.title_text = ""
        # Meta tag tracking
        self.in_meta = False
        self.meta_property = None
        self.meta_name = None
        # File links
        self.file_links = []
        self.current_link = None
        self.current_classes = []
        # Breadcrumb navigation tracking for bunkr.cr
        self.in_breadcrumb = False
        self.in_breadcrumb_item = False
        self.breadcrumb_items = []
    
    def handle_starttag(self, tag, attrs):
        """Process the opening tag and its attributes."""
        attrs_dict = dict(attrs)
        
        # Title tag for extracting album name from page title
        if tag == 'title':
            self.in_title = True
            self.title_text = ""
            return
        
        # Track h1 tags for album name
        if tag == 'h1':
            self.in_h1 = True
            if 'class' in attrs_dict:
                self.h1_class = attrs_dict['class']
            return
            
        # Track meta tags for album name
        if tag == 'meta':
            self.in_meta = True
            self.meta_property = attrs_dict.get('property')
            self.meta_name = attrs_dict.get('name')
            
            # Extract album name from meta tags
            if not self.album_name:
                if (self.meta_property == 'og:title' or self.meta_name == 'title') and 'content' in attrs_dict:
                    content = attrs_dict['content'].strip()
                    if content:
                        if ' - ' in content:
                            parts = content.split(' - ')
                            self.album_name = parts[0].strip()
                        else:
                            self.album_name = content
                    
        # Track navigation elements for bunkr.cr
        if not self.album_name and tag in ['nav', 'ol'] and 'class' in attrs_dict:
            classes = attrs_dict['class'] if isinstance(attrs_dict['class'], list) else attrs_dict['class'].split()
            if any(c for c in classes if 'breadcrumb' in c.lower() or 'navigation' in c.lower()):
                self.in_breadcrumb = True
        
        if self.in_breadcrumb and tag == 'li':
            self.in_breadcrumb_item = True
            
        # Track anchor tags for potential file links
        if tag == 'a' and 'href' in attrs_dict:
            href = attrs_dict['href']
            self.current_link = href
            self.current_classes = attrs_dict.get('class', '').split() if 'class' in attrs_dict else []
            
            # Process link immediately if it's a file link
            if href and ('/f/' in href or '/a/' in href or '/d/' in href):
                full_url = urljoin(self.base_url, href)
                if full_url not in self.file_links:
                    self.file_links.append(full_url)
            # Use regex pattern for more permissive matching
            elif href and re.search(r'/(f|a|d)/[a-zA-Z0-9]{8,}', href):
                full_url = urljoin(self.base_url, href)
                if full_url not in self.file_links:
                    self.file_links.append(full_url)
    
    def handle_endtag(self, tag):
        """Process the closing tag."""
        if tag == 'h1':
            self.in_h1 = False
            self.h1_class = None
        elif tag == 'title':
            self.in_title = False
            # If we haven't found an album name from h1, try to extract from title
            if not self.album_name and self.title_text:
                # Extract album name from title - usually in "Album Name - Bunkr" format
                title_parts = self.title_text.split(' - ')
                if len(title_parts) > 1:
                    self.album_name = title_parts[0].strip()
        elif tag == 'meta':
            self.in_meta = False
            self.meta_property = None
            self.meta_name = None
        elif tag == 'a':
            self.current_link = None
            self.current_classes = []
        elif tag in ['nav', 'ol'] and self.in_breadcrumb:
            self.in_breadcrumb = False
            # If we have breadcrumb items and no album name yet, use the last item
            if not self.album_name and len(self.breadcrumb_items) >= 2:
                self.album_name = self.breadcrumb_items[-1]
        elif tag == 'li' and self.in_breadcrumb_item:
            self.in_breadcrumb_item = False
    
    def handle_data(self, data):
        """Process the text content."""
        # Capture text in h1 as the album name
        if self.in_h1 and not self.album_name:
            if self.h1_class and 'block truncate' in self.h1_class:
                # This is the primary album name selector
                self.album_name = data.strip()
            elif not self.h1_class:
                # Fallback selector
                self.album_name = data.strip()
        
        # Capture title text
        if self.in_title:
            self.title_text += data
            
        # Capture breadcrumb items
        if self.in_breadcrumb_item:
            text = data.strip()
            if text:
                self.breadcrumb_items.append(text)
    
    def error(self, message):
        """Handle parsing errors gracefully."""
        logger.warning(f"HTML parser error: {message}")