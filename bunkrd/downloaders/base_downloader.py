"""
Base downloader class for BunkrDownloader application.
"""
import requests
import time
import os
import gc
import io
import logging
import datetime
from tqdm import tqdm
from ..config import (
    REQUEST_HEADERS, DEFAULT_RETRIES, 
    USE_PROXY, DEFAULT_PROXY, 
    RESPECT_ROBOTS_TXT, ERROR_MESSAGES
)
from ..utils.file_utils import get_url_data, mark_as_downloaded
from ..utils.request_utils import (
    create_session_with_random_ua, add_proxy_to_session,
    sleep_with_random_delay, get_random_user_agent,
    can_fetch, make_request_with_rate_limit
)

# Optimized chunk size for better performance with large files
# 1MB chunks balance memory usage and performance
CHUNK_SIZE = 1024 * 1024  # 1MB chunks

# Setup logger
logger = logging.getLogger(__name__)

class BaseDownloader:
    """
    Base class for downloading files from various services.
    
    This class provides common functionality for downloading files,
    with methods that can be overridden by specific service downloaders.
    """
    
    def __init__(self, session=None, proxy_url=None):
        """
        Initialize the downloader with a session.
        
        Args:
            session (requests.Session, optional): A requests session to use.
                If None, a new session will be created.
            proxy_url (str, optional): Proxy URL to use. If None and USE_PROXY is True,
                DEFAULT_PROXY will be used.
        """
        self.proxy_url = proxy_url if proxy_url is not None else (DEFAULT_PROXY if USE_PROXY else None)
        self.session = session if session else self.create_session()
    
    def create_session(self):
        """
        Create a new requests session with appropriate headers and proxy settings.
        
        Returns:
            requests.Session: A new session object
        """
        # Create session with random user agent
        session = create_session_with_random_ua()
        
        # Add proxy if configured
        if self.proxy_url:
            logger.info(f"Using proxy: {self.proxy_url}")
            session = add_proxy_to_session(session, self.proxy_url)
            
        return session

    def refresh_session(self):
        """
        Refresh the session with a new user agent.
        
        Returns:
            requests.Session: The refreshed session
        """
        self.session.headers['User-Agent'] = get_random_user_agent()
        logger.debug(f"Refreshed user agent: {self.session.headers['User-Agent'][:30]}...")
        return self.session
    
    def download(self, url, download_path, file_name=None, retries=DEFAULT_RETRIES):
        """
        Download a file from a URL.
        
        Args:
            url (str): URL to download from
            download_path (str): Directory to save the file to
            file_name (str, optional): File name to use. If None, extracted from URL.
            retries (int, optional): Number of retry attempts
            
        Returns:
            bool or dict: True if download was successful (legacy mode), or a dict with download stats
        """
        try:
            # First, check robots.txt if enabled
            if RESPECT_ROBOTS_TXT:
                user_agent = self.session.headers.get('User-Agent')
                if not can_fetch(url, user_agent):
                    logger.warning(ERROR_MESSAGES["robots_txt_denied"].format(url=url))
                    return False
            
            # Apply random delay before request
            sleep_with_random_delay()
            
            # Rotate user agent for this request
            self.refresh_session()
            
            url_data = get_url_data(url)
            file_name = url_data.get('file_name', 'unnamed_file') if file_name is None else file_name
            final_path = os.path.join(download_path, file_name)
            temp_path = f"{final_path}.part"
            
            # Display current date and time when URL is fetched - ensure no blank lines
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}]")
            print(f"FileName: {file_name}")
            print(f"FileURL: {url}")
            
            # Check if we have a partial download to resume
            resume_header = {}
            start_byte = 0
            if os.path.exists(temp_path):
                start_byte = os.path.getsize(temp_path)
                resume_header = {'Range': f'bytes={start_byte}-'}
                logger.info(f"Resuming download of {file_name} from byte {start_byte}")

            # Track download speed
            downloaded_bytes = start_byte
            download_start_time = time.time()
            download_speed = 0
            last_update_time = download_start_time
            last_update_bytes = start_byte

            try:
                # Use the session with a proper timeout and larger stream parameter
                # This will reduce the number of small chunks held in memory
                with self.session.get(
                    url, 
                    stream=True, 
                    timeout=30,  # Increased timeout for large files
                    headers=resume_header
                ) as r:
                    if start_byte > 0 and r.status_code == 416:
                        # Range not satisfiable, file might be complete or changed
                        logger.warning(f"Cannot resume download for \"{file_name}\": Range not satisfiable. Starting fresh.")
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        return self.download(url, download_path, file_name, retries)
                        
                    if start_byte > 0 and r.status_code != 206:
                        # Server doesn't support resuming, start from beginning
                        logger.warning(f"Server doesn't support resuming downloads for \"{file_name}\", starting from beginning")
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        return self.download(url, download_path, file_name, retries)
                        
                    if r.status_code not in (200, 201, 204, 206):
                        logger.error(ERROR_MESSAGES["http_error"].format(
                            code=r.status_code, 
                            message=r.reason
                        ))
                        return False
                        
                    if r.url == "https://bnkr.b-cdn.net/maintenance.mp4":
                        logger.error(ERROR_MESSAGES["maintenance"])
                        return False

                    # Determine total file size
                    if r.status_code == 206:
                        # For resumed downloads, content-range header has total size
                        content_range = r.headers.get('content-range', '')
                        if content_range:
                            file_size = int(content_range.split('/')[-1])
                        else:
                            file_size = start_byte + int(r.headers.get('content-length', 0))
                    else:
                        file_size = int(r.headers.get('content-length', -1))
                    
                    # Open the file in append mode if resuming, otherwise write mode
                    mode = 'ab' if start_byte > 0 else 'wb'
                    
                    with open(temp_path, mode) as f:
                        # Define ANSI color codes
                        blue = '\033[34m'
                        green = '\033[32m'
                        orange = '\033[33m'
                        reset = '\033[0m'
                        
                        # Configure tqdm with proper color initialization
                        tqdm_kwargs = {
                            'total': file_size,
                            'initial': start_byte,
                            'unit': 'B',
                            'unit_scale': True,
                            'dynamic_ncols': True,
                            'leave': True,
                            'mininterval': 0.5,
                            'bar_format': f'{{bar}} {blue}{{percentage:3.0f}}%{reset} of {{n_fmt}}/{{total_fmt}} at {green}{{rate_fmt}}{reset} ETA {orange}[{{remaining}}]{reset}'
                        }
                        
                        with tqdm(**tqdm_kwargs) as pbar:
                            # Use optimized chunk size
                            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                if chunk:  # Filter out keep-alive new chunks
                                    f.write(chunk)
                                    f.flush()  # Ensure data is written to disk immediately
                                    pbar.update(len(chunk))
                                    
                                    # Update download speed calculations
                                    downloaded_bytes += len(chunk)
                                    current_time = time.time()
                                    if current_time - last_update_time >= 1.0:  # Update speed every second
                                        chunk_time = current_time - last_update_time
                                        chunk_bytes = downloaded_bytes - last_update_bytes
                                        if chunk_time > 0:  # Avoid division by zero
                                            download_speed = chunk_bytes / chunk_time
                                        last_update_time = current_time
                                        last_update_bytes = downloaded_bytes
                            
                            # Explicitly flush at the end to ensure all data is written
                            f.flush()
                            os.fsync(f.fileno())
                    
                    # Calculate total download time and speed
                    total_download_time = time.time() - download_start_time
                    if total_download_time > 0:  # Avoid division by zero
                        overall_speed = (downloaded_bytes - start_byte) / total_download_time
                    else:
                        overall_speed = 0
                    
                    # Rename the .part file to the final filename after successful download
                    if os.path.exists(temp_path):
                        os.rename(temp_path, final_path)

                    # Force garbage collection to free up memory
                    gc.collect()
                    
                # Verify file integrity
                if file_size > -1:
                    try:
                        downloaded_file_size = os.stat(final_path).st_size
                        if downloaded_file_size != file_size:
                            logger.error(f"{file_name} size check failed: Expected: {file_size}, Got: {downloaded_file_size}. File may be corrupt.")
                            return False
                    except OSError as e:
                        logger.error(f"Error checking file size for \"{file_name}\": {str(e)}")
                        return False

                # Mark as successfully downloaded
                mark_as_downloaded(url, download_path)
                logger.info(f"Successfully downloaded {file_name} ({downloaded_file_size} bytes) at {overall_speed/1024/1024:.2f} MB/s")
                
                # Return detailed stats instead of just True
                return {
                    'success': True,
                    'file_name': file_name,
                    'file_size': downloaded_file_size,
                    'download_time': total_download_time,
                    'speed': overall_speed
                }
                
            except requests.Timeout:
                logger.error(ERROR_MESSAGES["timeout"].format(url=url))
                return False
            except requests.RequestException as e:
                logger.error(ERROR_MESSAGES["network_error"].format(url=url, error=str(e)))
                return False
                
        except Exception as e:
            logger.error(ERROR_MESSAGES["download_error"].format(url=url, error=str(e)))
            return False
            
    def download_with_retry(self, url, download_path, file_name=None, retries=DEFAULT_RETRIES):
        """
        Download a file with multiple retry attempts.
        
        Args:
            url (str): URL to download from
            download_path (str): Directory to save the file to
            file_name (str, optional): File name to use. If None, extracted from URL.
            retries (int, optional): Number of retry attempts
            
        Returns:
            bool or dict: True if download was successful (legacy mode), or a dict with download stats
        """
        for i in range(1, retries + 1):
            try:
                logger.info(f"Downloading {url} (attempt {i}/{retries})")
                result = self.download(url, download_path, file_name)
                
                # Handle both legacy (bool) and new (dict) return types
                if isinstance(result, dict):
                    if result.get('success', False):
                        return result
                elif result:  # Legacy boolean return
                    return True
                    
                if i < retries:
                    # Use variable delay between retries (increasing with each attempt)
                    delay = 2 + (i - 1) * 0.5
                    logger.warning(f"Download failed. Retrying in {delay:.1f} seconds... ({i}/{retries})")
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error while downloading: {str(e)}")
                if i == retries:
                    return False
                delay = 2 + (i - 1) * 0.5
                logger.warning(f"Retrying in {delay:.1f} seconds... ({i}/{retries})")
                time.sleep(delay)
                
        return False

    def make_api_request(self, method, url, **kwargs):
        """
        Make an API request with rate limiting and other protections.
        
        Args:
            method (str): HTTP method (get, post, etc.)
            url (str): URL to request
            **kwargs: Additional arguments to pass to the request method
            
        Returns:
            requests.Response: The response from the server
        """
        logger.debug(f"Making API request: {method.upper()} {url}")
        return make_request_with_rate_limit(
            self.session, 
            method, 
            url, 
            check_robots=RESPECT_ROBOTS_TXT,
            **kwargs
        )