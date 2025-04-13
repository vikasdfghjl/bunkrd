"""
Main controller for the BunkrDownloader application.
"""
import os
import time  # Import time module for CONCURRENT_DELAY
import re
import requests
import concurrent.futures
import logging
from urllib.parse import urlparse, urljoin
from tqdm import tqdm

from .downloaders.factory import DownloaderFactory
from .parsers.factory import ParserFactory
from .utils.file_utils import (
    get_and_prepare_download_path, 
    get_already_downloaded_url,
    write_url_to_list
)
from .utils.request_utils import (
    create_session_with_random_ua,
    add_proxy_to_session,
    sleep_with_random_delay
)
from .config import USE_PROXY, DEFAULT_PROXY, DEFAULT_CONCURRENT_DOWNLOADS, CONCURRENT_DELAY

# Setup logger
logger = logging.getLogger(__name__)

# Define URL validation regex patterns
VALID_URL_PATTERN = re.compile(
    r'^(?:http|https)://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or ipv4
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

# Define allowed domains
ALLOWED_DOMAINS = [
    'bunkr.sk', 'bunkr.is', 'bunkr.la', 'bunkr.cr', 
    'cyberdrop.me', 'cyberdrop.cc',
    # Add more allowed domains as needed
]

class DownloadController:
    """
    Main controller class for orchestrating the download process.
    
    This class handles the workflow of parsing album pages, getting 
    download URLs, and downloading files.
    """
    
    def __init__(self, proxy_url=None, max_concurrent_downloads=None, log_level=logging.INFO):
        """
        Initialize the controller with a shared session.
        
        Args:
            proxy_url (str, optional): Proxy URL to use. If None and USE_PROXY is True,
                DEFAULT_PROXY will be used.
            max_concurrent_downloads (int, optional): Maximum number of concurrent downloads.
                If None, DEFAULT_CONCURRENT_DOWNLOADS will be used.
            log_level (int, optional): Logging level. Default is logging.INFO.
        """
        self.proxy_url = proxy_url if proxy_url is not None else (DEFAULT_PROXY if USE_PROXY else None)
        self.session = self._create_session()
        self.max_concurrent_downloads = max_concurrent_downloads or DEFAULT_CONCURRENT_DOWNLOADS
        logger.setLevel(log_level)
        
    def _create_session(self):
        """
        Create a new session with random user agent and proxy support.
        
        Returns:
            requests.Session: The configured session
        """
        # Create session with random user agent
        session = create_session_with_random_ua()
        
        # Add proxy if configured
        if self.proxy_url:
            session = add_proxy_to_session(session, self.proxy_url)
            
        return session
    
    def _validate_url(self, url):
        """
        Validate a URL to ensure it's safe to process.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if the URL is valid and safe, False otherwise
        """
        try:
            # Basic URL format validation
            if not VALID_URL_PATTERN.match(url):
                logger.error(f"Invalid URL format: {url}")
                return False
            
            # Parse the URL to get its components
            parsed_url = urlparse(url)
            
            # Check if the domain is in our allowed list
            domain = parsed_url.netloc
            is_allowed = any(allowed_domain in domain for allowed_domain in ALLOWED_DOMAINS)
            
            if not is_allowed:
                logger.error(f"Domain not in allowed list: {domain}")
                return False
                
            # Check for potentially dangerous paths that could indicate path traversal attempts
            if '..' in parsed_url.path or '//' in parsed_url.path.replace('://', ''):
                logger.error(f"Potentially unsafe path in URL: {url}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error validating URL {url}: {str(e)}")
            return False
        
    def process_url(self, url, download_dir=None):
        """
        Process a URL which could be either an album or a direct file.
        
        Args:
            url (str): URL to process
            download_dir (str, optional): Directory to download files to
            
        Returns:
            bool: True if processing was successful, False otherwise
        """
        try:
            # Ensure URL has http scheme
            if not url.startswith('http'):
                url = f'https://{url}'
            
            # Validate URL before processing
            if not self._validate_url(url):
                logger.error(f"Skipping invalid or unsafe URL: {url}")
                return False
                
            # Parse URL to determine if it's an album or file
            parsed_url = urlparse(url)
            if parsed_url.path and '/f/' in parsed_url.path:
                # It's a file URL, download it directly
                return self._download_file(url, download_dir)
            else:
                # It's an album URL, process it
                return self._process_album(url, download_dir)
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            return False
            
    def process_file(self, file_path, download_dir=None):
        """
        Process URLs from a file.
        
        Args:
            file_path (str): Path to file containing URLs
            download_dir (str, optional): Directory to download files to
            
        Returns:
            bool: True if all URLs were processed successfully, False otherwise
        """
        try:
            # Validate file_path to prevent directory traversal
            file_path = os.path.abspath(os.path.normpath(file_path))
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                logger.error(f"File not found or is not a regular file: {file_path}")
                return False
                
            with open(file_path, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]
                
            # Create overall progress bar for all URLs
            logger.info(f"Processing {len(urls)} URLs from file: {file_path}")
            success_count = 0
            
            with tqdm(total=len(urls), desc="Overall Progress", unit="urls") as pbar:
                for url in urls:
                    logger.info(f"Processing URL: {url}")
                    if self.process_url(url, download_dir):
                        success_count += 1
                    pbar.update(1)
                
            logger.info(f"Completed: {success_count}/{len(urls)} URLs processed successfully")
            return success_count == len(urls)
        except IOError as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return False
            
    def _process_album(self, album_url, download_dir=None):
        """
        Process an album URL.
        
        Args:
            album_url (str): URL of the album to process
            download_dir (str, optional): Directory to download files to
            
        Returns:
            bool: True if album was processed successfully, False otherwise
        """
        try:
            # Get the appropriate parser
            parser = ParserFactory.get_parser(album_url, self.session, self.proxy_url)
            
            # Parse the album
            logger.info(f"Parsing album: {album_url}")
            album_data = parser.parse_album(album_url)
            
            if not album_data["files"]:
                logger.error(f"No files found in album: {album_url}")
                return False
                
            # Prepare the download path
            album_download_dir = get_and_prepare_download_path(download_dir, album_data["album_name"])
            already_downloaded = get_already_downloaded_url(album_download_dir)
            
            # Filter out already downloaded files
            files_to_download = []
            for file_url in album_data["files"]:
                if file_url in already_downloaded:
                    logger.info(f"Skipping already downloaded: {file_url}")
                    continue
                files_to_download.append(file_url)
                write_url_to_list(file_url, album_download_dir)
            
            total_files = len(album_data["files"])
            remaining_files = len(files_to_download)
            logger.info(f"Found {total_files} files in album: {album_data['album_name']}, {remaining_files} to download")
            
            if not files_to_download:
                logger.info(f"All files in album {album_data['album_name']} are already downloaded")
                return True
            
            # Download files concurrently
            return self._download_files_concurrently(files_to_download, album_download_dir)
        except Exception as e:
            logger.error(f"Error processing album {album_url}: {str(e)}")
            return False
            
    def _download_files_concurrently(self, file_urls, download_dir):
        """
        Download multiple files concurrently using a thread pool.
        
        Args:
            file_urls (list): List of file URLs to download
            download_dir (str): Directory to download files to
            
        Returns:
            bool: True if all files were downloaded successfully, False otherwise
        """
        if not file_urls:
            return True
            
        logger.info(f"Starting concurrent downloads with {min(self.max_concurrent_downloads, len(file_urls))} workers")
        results = []
        active_downloads = 0
        error_count = 0
        
        # Create a progress bar for overall download progress
        print(f"\nTotal files to download: {len(file_urls)}")
        print(f"Download destination: {os.path.abspath(download_dir)}")
        print("Starting downloads...\n")

        # Use a slightly lower number of workers if there are many files
        # This helps prevent overwhelming the server
        if len(file_urls) > 10:
            actual_workers = min(self.max_concurrent_downloads, max(2, self.max_concurrent_downloads - 1))
        else:
            actual_workers = self.max_concurrent_downloads
            
        logger.info(f"Using {actual_workers} concurrent download threads")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # Submit initial batch of downloads
            futures_to_url = {}
            for i, url in enumerate(file_urls[:actual_workers]):
                # Add a small delay between submitting each download task
                if i > 0:
                    time.sleep(CONCURRENT_DELAY)
                futures_to_url[executor.submit(self._download_file, url, download_dir)] = url
                active_downloads += 1
            
            # Process results and add new downloads as others complete
            remaining_urls = file_urls[actual_workers:]
            completed_count = 0
            
            # If we encounter too many consecutive errors, reduce concurrency
            consecutive_errors = 0
            reduced_concurrency = False
            
            while futures_to_url:
                # Wait for the next future to complete
                done, _ = concurrent.futures.wait(
                    futures_to_url.keys(),
                    return_when=concurrent.futures.FIRST_COMPLETED
                )
                
                for future in done:
                    url = futures_to_url.pop(future)
                    active_downloads -= 1
                    completed_count += 1
                    
                    try:
                        success = future.result()
                        if success:
                            consecutive_errors = 0
                        else:
                            error_count += 1
                            consecutive_errors += 1
                        
                        results.append(success)
                        
                        # Print a simple status update after each file
                        print(f"Progress: {completed_count}/{len(file_urls)} files completed")
                        
                        # If we encounter too many consecutive errors, reduce concurrency
                        if consecutive_errors >= 3 and not reduced_concurrency:
                            reduced_workers = max(1, actual_workers // 2)
                            logger.warning(f"Too many consecutive errors, reducing concurrency to {reduced_workers} workers")
                            actual_workers = reduced_workers
                            reduced_concurrency = True
                            # Allow some time for the system to recover
                            time.sleep(3.0)
                        
                    except Exception as e:
                        logger.error(f"Error processing {url}: {str(e)}")
                        results.append(False)
                        error_count += 1
                        consecutive_errors += 1
                        print(f"Error downloading: {url}")
                    
                    # Submit a new download task if there are URLs remaining and we haven't hit our concurrency limit
                    if remaining_urls and active_downloads < actual_workers:
                        next_url = remaining_urls.pop(0)
                        # Add a small delay between submitting new download tasks
                        time.sleep(CONCURRENT_DELAY)
                        futures_to_url[executor.submit(self._download_file, next_url, download_dir)] = next_url
                        active_downloads += 1
        
        # Check if all downloads were successful
        success_count = sum(1 for r in results if r)
        print(f"\nDownload complete: {success_count}/{len(file_urls)} files downloaded successfully")
        logger.info(f"Download complete: {success_count}/{len(file_urls)} files downloaded successfully")
        return all(results)
            
    def _download_file(self, file_url, download_dir=None):
        """
        Download a single file.
        
        Args:
            file_url (str): URL of the file to download
            download_dir (str, optional): Directory to download the file to
            
        Returns:
            bool: True if file was downloaded successfully, False otherwise
        """
        try:
            # Prepare download path
            download_path = get_and_prepare_download_path(download_dir, None)
            
            # Check if already downloaded
            already_downloaded = get_already_downloaded_url(download_path)
            if file_url in already_downloaded:
                logger.info(f"Skipping already downloaded: {file_url}")
                return True
                
            # Get the appropriate downloader
            downloader = DownloaderFactory.get_downloader(file_url, self.session, self.proxy_url)
            
            # Get the real download URL
            logger.info(f"Getting download URL for: {file_url}")
            download_info = downloader.get_real_download_url(file_url)
            
            if not download_info:
                logger.error(f"Failed to get download URL for: {file_url}")
                return False
                
            # Download the file
            success = downloader.download_with_retry(
                download_info["url"], 
                download_path
            )
            
            # If download was successful, add to already downloaded list
            if success:
                from .utils.file_utils import mark_as_downloaded
                mark_as_downloaded(file_url, download_path)
                
            return success
        except Exception as e:
            logger.error(f"Error downloading file {file_url}: {str(e)}")
            return False