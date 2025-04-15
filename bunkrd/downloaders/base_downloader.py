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
    sleep_with_random_delay,
    can_fetch, make_request_with_rate_limit,
    measure_connection_speed,
    check_memory_usage,
    clear_memory_for_large_download
)
from ..utils.session_factory import SessionFactory

# Chunk size constants
MIN_CHUNK_SIZE = 64 * 1024     # 64 KB
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB
MAX_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB

# Memory thresholds for triggering collection during download
MEMORY_CHECK_FREQUENCY = 50  # Check memory every N chunks
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB

# Connection speed thresholds in bytes/second
SLOW_CONNECTION = 256 * 1024    # 256 KB/s
MEDIUM_CONNECTION = 1024 * 1024  # 1 MB/s
FAST_CONNECTION = 5 * 1024 * 1024  # 5 MB/s

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
        self.connection_speed = None
        self.adaptive_chunk_size = DEFAULT_CHUNK_SIZE
    
    def create_session(self):
        """
        Create a new requests session with appropriate headers and proxy settings.
        
        Returns:
            requests.Session: A new session object
        """
        return SessionFactory.create_session(self.proxy_url)
    
    def refresh_session(self):
        """
        Refresh the session with a new user agent.
        
        Returns:
            requests.Session: The refreshed session
        """
        return SessionFactory.refresh_session(self.session)

    def get_adaptive_chunk_size(self, url=None):
        """
        Calculate optimal chunk size based on connection speed.
        
        If no connection speed measurement is available, this will
        measure the connection speed to the given URL.
        
        Args:
            url (str, optional): URL to measure connection speed with
            
        Returns:
            int: Optimal chunk size in bytes
        """
        # Use existing speed measurement if available and recent
        if not self.connection_speed and url:
            self.connection_speed = measure_connection_speed(self.session, url)
        
        # If we couldn't measure speed, use default chunk size
        if not self.connection_speed:
            logger.debug("Could not measure connection speed. Using default chunk size.")
            return DEFAULT_CHUNK_SIZE
            
        # Calculate optimal chunk size based on connection speed
        if self.connection_speed < SLOW_CONNECTION:
            # For slow connections, use smaller chunks
            chunk_size = MIN_CHUNK_SIZE
            logger.debug(f"Slow connection detected ({self.connection_speed/1024:.1f} KB/s). Using {chunk_size/1024:.1f} KB chunks.")
        elif self.connection_speed < MEDIUM_CONNECTION:
            # For medium connections, scale between MIN and DEFAULT
            scale_factor = (self.connection_speed - SLOW_CONNECTION) / (MEDIUM_CONNECTION - SLOW_CONNECTION)
            chunk_size = MIN_CHUNK_SIZE + scale_factor * (DEFAULT_CHUNK_SIZE - MIN_CHUNK_SIZE)
            logger.debug(f"Medium connection detected ({self.connection_speed/1024/1024:.2f} MB/s). Using {chunk_size/1024:.1f} KB chunks.")
        elif self.connection_speed < FAST_CONNECTION:
            # For faster connections, scale between DEFAULT and MAX
            scale_factor = (self.connection_speed - MEDIUM_CONNECTION) / (FAST_CONNECTION - MEDIUM_CONNECTION)
            chunk_size = DEFAULT_CHUNK_SIZE + scale_factor * (MAX_CHUNK_SIZE - DEFAULT_CHUNK_SIZE)
            logger.debug(f"Fast connection detected ({self.connection_speed/1024/1024:.2f} MB/s). Using {chunk_size/1024/1024:.2f} MB chunks.")
        else:
            # For very fast connections, use maximum chunk size
            chunk_size = MAX_CHUNK_SIZE
            logger.debug(f"Very fast connection detected ({self.connection_speed/1024/1024:.2f} MB/s). Using {chunk_size/1024/1024:.2f} MB chunks.")
            
        return int(chunk_size)
    
    def update_connection_speed(self, bytes_downloaded, download_time):
        """
        Update the connection speed measurement based on actual download data.
        
        Args:
            bytes_downloaded (int): Number of bytes downloaded
            download_time (float): Time taken to download in seconds
        """
        if download_time > 0 and bytes_downloaded > 0:
            # Calculate speed as moving average (30% new, 70% previous)
            new_speed = bytes_downloaded / download_time
            if self.connection_speed:
                self.connection_speed = 0.3 * new_speed + 0.7 * self.connection_speed
            else:
                self.connection_speed = new_speed
                
            logger.debug(f"Updated connection speed: {self.connection_speed/1024/1024:.2f} MB/s")
    
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
            
            # Log download information instead of printing
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[{current_time}] Starting download")
            logger.info(f"FileName: {file_name}")
            logger.info(f"FileURL: {url}")
            
            # Check if we have a partial download to resume
            resume_header = {}
            start_byte = 0
            if os.path.exists(temp_path):
                start_byte = os.path.getsize(temp_path)
                resume_header = {'Range': f'bytes={start_byte}-'}
                logger.info(f"Resuming download of {file_name} from byte {start_byte}")

            # Determine optimal chunk size for this connection
            self.adaptive_chunk_size = self.get_adaptive_chunk_size(url)

            # Track download speed
            downloaded_bytes = start_byte
            download_start_time = time.time()
            download_speed = 0
            last_update_time = download_start_time
            last_update_bytes = start_byte
            
            # Make initial HEAD request to get file size
            try:
                with self.session.head(url, timeout=10, headers=resume_header) as head_resp:
                    if 'content-length' in head_resp.headers:
                        file_size = int(head_resp.headers.get('content-length', 0))
                        
                        # If file is large, prepare memory
                        if file_size > LARGE_FILE_THRESHOLD:
                            logger.info(f"Large file detected ({file_size/1024/1024:.1f} MB). Preparing memory.")
                            clear_memory_for_large_download()
            except Exception:
                # If HEAD request fails, we'll still try the GET request
                file_size = -1

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
                        
                    if not (200 <= r.status_code < 300):
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
                    
                    # For large files, prepare memory again if not already done
                    if file_size > LARGE_FILE_THRESHOLD:
                        clear_memory_for_large_download()
                    
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
                            # Use adaptive chunk size
                            chunk_count = 0
                            current_chunk_size = self.adaptive_chunk_size
                            
                            for chunk in r.iter_content(chunk_size=current_chunk_size):
                                if chunk:  # Filter out keep-alive new chunks
                                    f.write(chunk)
                                    f.flush()  # Ensure data is written to disk immediately
                                    chunk_size = len(chunk)
                                    pbar.update(chunk_size)
                                    
                                    # Update download speed calculations
                                    downloaded_bytes += chunk_size
                                    current_time = time.time()
                                    chunk_count += 1
                                    
                                    # Check memory usage periodically
                                    if chunk_count % MEMORY_CHECK_FREQUENCY == 0:
                                        check_memory_usage()
                                    
                                    # Every 10 chunks, reassess connection speed and chunk size
                                    if chunk_count % 10 == 0:
                                        if current_time - last_update_time >= 1.0:  # Update at least once per second
                                            chunk_time = current_time - last_update_time
                                            chunk_bytes = downloaded_bytes - last_update_bytes
                                            
                                            if chunk_time > 0:  # Avoid division by zero
                                                # Update connection speed
                                                download_speed = chunk_bytes / chunk_time
                                                self.update_connection_speed(chunk_bytes, chunk_time)
                                                
                                                # Adjust chunk size based on new speed measurement
                                                new_chunk_size = self.get_adaptive_chunk_size()
                                                
                                                # Gradually change chunk size to avoid sudden jumps
                                                if new_chunk_size != current_chunk_size:
                                                    current_chunk_size = int(0.7 * current_chunk_size + 0.3 * new_chunk_size)
                                                    logger.debug(f"Adjusted chunk size to {current_chunk_size/1024:.1f} KB")
                                                
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
                    
                    # Update connection speed for future downloads
                    self.update_connection_speed(downloaded_bytes - start_byte, total_download_time)
                    
                    # Rename the .part file to the final filename after successful download
                    if os.path.exists(temp_path):
                        os.rename(temp_path, final_path)

                    # Force garbage collection to free up memory after the download
                    # This helps prevent memory fragmentation when downloading many files
                    check_memory_usage(force_collect=True)
                    
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
                    'speed': overall_speed,
                    'final_chunk_size': current_chunk_size
                }
                
            except requests.Timeout:
                logger.error(ERROR_MESSAGES["timeout"].format(url=url))
                return False
            except requests.RequestException as e:
                logger.error(ERROR_MESSAGES["network_error"].format(url=url, error=str(e)))
                return False
            finally:
                # Clean up any large response objects still in memory
                check_memory_usage(force_collect=True)
                
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
                
                # Ensure we have clean memory before each attempt
                if i > 1:  # Only force collection on retry attempts
                    check_memory_usage(force_collect=True)
                
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
        
        This method returns a context manager that can be used with 'with' statements
        to ensure proper resource cleanup after the request completes.
        
        Args:
            method (str): HTTP method (get, post, etc.)
            url (str): URL to request
            **kwargs: Additional arguments to pass to the request method
            
        Returns:
            requests.Response: The response from the server that can be used as a context manager
        """
        logger.debug(f"Making API request: {method.upper()} {url}")
        
        # Check memory before API requests to prevent OOM during large responses
        check_memory_usage()
        
        try:
            response = make_request_with_rate_limit(
                self.session, 
                method, 
                url, 
                check_robots=RESPECT_ROBOTS_TXT,
                **kwargs
            )
            return response
        finally:
            # Clean up potential large JSON responses after request
            if not kwargs.get('stream', False):
                check_memory_usage()