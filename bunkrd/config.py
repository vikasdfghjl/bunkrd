"""
Configuration settings for the BunkrDownloader application.
Contains constants and settings used throughout the application.
"""
import os
import logging
from .utils.security_utils import load_secret_from_env, initialize_secret_key

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API URLs
BUNKR_VS_API_URL = "https://bunkr.cr/api/vs"

# Secret key settings - using the same key as in the working script
SECRET_KEY_BASE = "SECRET_KEY_"
SECRET_KEY_ENV_VAR = "BUNKRDOWNLOADER_SECRET_KEY_BASE"

# Default settings
DEFAULT_RETRIES = 10
DEFAULT_DOWNLOAD_PATH = "downloads"

# Rate limiting settings
MIN_REQUEST_DELAY = 1.0  # Minimum delay between requests in seconds
MAX_REQUEST_DELAY = 3.0  # Maximum delay between requests in seconds

# Proxy settings
USE_PROXY = False  # Set to True to enable proxy
DEFAULT_PROXY = None  # Set to your proxy URL (e.g., 'socks5://127.0.0.1:9050')

# Concurrency settings
DEFAULT_CONCURRENT_DOWNLOADS = 3  # Default number of concurrent downloads (keep low to avoid bans)
CONCURRENT_DELAY = 1.5  # Delay between starting concurrent downloads (seconds)

# Parser settings
USE_INCREMENTAL_PARSER = True  # Use memory-efficient incremental HTML parser for large albums
INCREMENTAL_CHUNK_SIZE = 8192  # Size of chunks (in bytes) for incremental parsing (8KB default)

# HTTP Request Headers
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
    'Referer': 'https://bunkr.sk/',
}

# List of user agents to rotate through
DEFAULT_USER_AGENTS = [
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    # Firefox on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    # Firefox on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0',
    # Safari on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0',
    # Mobile - Chrome on Android
    'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36',
    # Mobile - Safari on iOS
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]

# File paths
ALREADY_DOWNLOADED_FILE = "already_downloaded.txt"
URL_LIST_FILE = "url_list.txt"

# Error messages
ERROR_MESSAGES = {
    "no_input_method": "No input method specified. Please use -u/--url for a single URL, -f/--file for a file containing URLs, or -i/--interactive for interactive mode.",
    "no_url_file": "No URL or file provided. Please provide a URL with -u/--url or a file with -f/--file containing URLs to download.",
    "both_url_file": "Please provide only one URL or file, not both. Use -u/--url for a single URL or -f/--file for a file containing URLs.",
    "dir_create_error": "Error creating directory: {path}. Please check if you have write permissions to this location or try a different download path with -o/--output.",
    "file_write_error": "Error writing file: {path}. Check disk space and permissions or try a different download path with -o/--output.",
    "maintenance": "Server is currently down for maintenance. Please try again later or check if the site is available in your browser.",
    "http_error": "HTTP error {code}: {message}. This may be due to rate limiting, try increasing delay with --min-delay and --max-delay options or use a proxy with --proxy.",
    "no_items": "No downloadable items found in {url}. The album may be empty or require authentication. Check that the URL is correct and accessible in your browser.",
    "unknown_album": "Could not determine album name. Using 'unknown_album' as directory name.",
    "download_error": "Error downloading {url}: {error}. Try using a proxy with --proxy or increase delay between requests with --min-delay and --max-delay.",
    "timeout": "Timeout downloading {url}. The server may be slow or overloaded. Try again later or use --min-delay and --max-delay to increase wait times.",
    "json_error": "JSON parsing error for {url}: {error}. The site's content structure may have changed. Please report this issue.",
    "network_error": "Network error when accessing {url}: {error}. Check your internet connection or try using a proxy with --proxy.",
    "robots_txt_denied": "Access denied by robots.txt for {url}. Use --no-robots-check to bypass this check (not recommended).",
    "invalid_url": "Invalid URL format: {url}. Please provide a valid URL including the http:// or https:// protocol.",
    "unsupported_domain": "Unsupported domain: {domain}. This application currently only supports {supported_domains}.",
    "file_not_found": "File not found: {path}. Please check that the file exists and you have read permissions.",
    "path_too_long": "Path too long: {path}. Try using a shorter download directory path with -o/--output."
}

# Robots.txt settings
RESPECT_ROBOTS_TXT = False  # Set to False to ignore robots.txt

# URL validation
VALIDATE_URLS = True  # Set to False to disable URL validation (not recommended)
ALLOWED_URL_PATTERNS = [
    r'https?://(?:.*\.)?bunkr\.[a-z]{2,}/.*',
    r'https?://(?:.*\.)?cyberdrop\.[a-z]{2,}/.*',
]

def get_version():
    """Get the application version."""
    try:
        from . import __version__
        return __version__
    except (ImportError, AttributeError):
        return "unknown"