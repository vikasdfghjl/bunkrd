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

# Import our new formatting functions from cli module
try:
    from .cli import format_text, draw_box, draw_fancy_progress_bar
except ImportError:
    # Fallbacks in case the imports fail
    def format_text(text, color=None, bold=False):
        return text
        
    def draw_box(text, width=None, title=None, color='cyan', padding=1):
        if title:
            return f"=== {title} ===\n{text}\n"
        return f"=== {text} ==="
        
    def draw_fancy_progress_bar(current, total, width=30, speed=None):
        """Draw a simple progress bar with percentage and optional speed."""
        progress = int(width * current / total) if total > 0 else 0
        percentage = f"{current / total * 100:.1f}%" if total > 0 else "0.0%"
        
        bar = '=' * progress + ' ' * (width - progress)
        
        basic_info = f"[{bar}] {percentage} ({current}/{total})"
        
        if speed:
            return f"{basic_info} | Speed: {speed}/s"
        return basic_info

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
        
        # Configure logger to output to file instead of console
        self._configure_logging(log_level)
        
    def _configure_logging(self, log_level):
        """
        Configure logging to write to a file instead of displaying in the console.
        
        Args:
            log_level (int): The logging level to use
        """
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Configure file handler for logging
        log_file = os.path.join(log_dir, 'bunkr_downloader.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        
        # Set formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Configure root logger to use the file handler instead of console
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Remove any existing handlers (including console handlers)
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        # Add the file handler
        root_logger.addHandler(file_handler)
        
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
                
            # Return True if the URL passes all validation checks
            return True
        except Exception as e:
            # Log any exceptions that occur during URL validation
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
            # Ensure URL has http scheme - automatically prepend https:// if missing
            if not url.startswith('http'):
                url = f'https://{url}'
            
            # Validate URL before processing to ensure it's safe and in the correct format
            if not self._validate_url(url):
                # If validation fails, display error message and abort processing
                error_msg = f"Skipping invalid or unsafe URL: {url}"
                logger.error(error_msg)
                print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
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
            error_msg = f"Error processing URL {url}: {str(e)}"
            logger.error(error_msg)
            print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
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
                error_msg = f"File not found or is not a regular file: {file_path}"
                logger.error(error_msg)
                print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
                return False
                
            with open(file_path, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]
                
            # Create overall progress bar for all URLs
            logger.info(f"Processing {len(urls)} URLs from file: {file_path}")
            
            # Show file info header
            info_box = draw_box(
                f"Total URLs: {len(urls)}\n"
                f"Download path: {os.path.abspath(download_dir)}",
                title="File Processing", color="blue", padding=1
            )
            print(f"\n{info_box}\n")
            
            success_count = 0
            
            with tqdm(total=len(urls), desc="Overall Progress", unit="urls") as pbar:
                for i, url in enumerate(urls):
                    # Display URL being processed - remove extra newline
                    print(f"{format_text('URL', 'cyan')} {i+1}/{len(urls)}: {format_text(url, 'yellow')}")
                    print(format_text('─' * (len(url) + 20), 'blue'))
                    
                    logger.info(f"Processing URL: {url}")
                    if self.process_url(url, download_dir):
                        success_count += 1
                    pbar.update(1)
                    
                    # Add a separator between URLs for clearer output
                    if i < len(urls) - 1:
                        print(format_text('\n' + '─' * 60 + '\n', 'blue'))
                
            # Show final summary in a box
            result = f"{success_count}/{len(urls)} URLs processed successfully"
            if success_count == len(urls):
                summary = draw_box(result, title="Complete", color="green")
            else:
                summary = draw_box(
                    f"{result}\n{len(urls) - success_count} URLs failed", 
                    title="Completed with Errors", color="yellow"
                )
            print(f"\n{summary}\n")
            
            logger.info(f"Completed: {success_count}/{len(urls)} URLs processed successfully")
            return success_count == len(urls)
        except IOError as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            logger.error(error_msg)
            print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
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
            print(f"\n{draw_box('Parsing album page...', title='Album', color='cyan')}\n")
            
            album_data = parser.parse_album(album_url)
            
            if not album_data["files"]:
                error_msg = f"No files found in album: {album_url}"
                logger.error(error_msg)
                print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
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
            
            # Display album information in a box
            download_info = (
                f"Album name: {album_data['album_name']}\n"
                f"Total files: {total_files}\n"
                f"Already downloaded: {total_files - remaining_files}\n"
                f"Files to download: {remaining_files}\n"
                f"Download path: {os.path.abspath(album_download_dir)}"
            )
            print(f"\n{draw_box(download_info, title='Album Info', color='cyan', padding=1)}\n")
            
            if not files_to_download:
                complete_msg = f"All files in album {album_data['album_name']} are already downloaded"
                logger.info(complete_msg)
                print(f"\n{draw_box(complete_msg, title='Complete', color='green')}\n")
                return True
            
            # Download files based on concurrency setting
            if self.max_concurrent_downloads > 1:
                # Download files concurrently if max_concurrent_downloads > 1
                return self._download_files_concurrently(files_to_download, album_download_dir)
            else:
                # Download files sequentially one by one
                return self._download_files_sequentially(files_to_download, album_download_dir)
        except Exception as e:
            error_msg = f"Error processing album {album_url}: {str(e)}"
            logger.error(error_msg)
            print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
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
        
        # Create a header box for the download section
        download_mode = f"Concurrent mode ({min(self.max_concurrent_downloads, len(file_urls))} workers)"
        header = draw_box(
            f"Total files: {len(file_urls)}\n"
            f"Download path: {os.path.abspath(download_dir)}\n"
            f"Mode: {download_mode}",
            title="Download Starting", color="blue", padding=1
        )
        print(f"\n{header}\n")

        results = []
        active_downloads = 0
        error_count = 0
        total_size = 0
        total_time = 0
        skipped = 0
        
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
            
            # Track current download speed
            current_speed = 0
            
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
                        result = future.result()
                        
                        # Process download stats
                        if isinstance(result, dict) and result.get('success'):
                            if not result.get('skipped', False):
                                if 'speed' in result and 'file_size' in result:
                                    # Track speed of most recent download for progress bar
                                    current_speed = result['speed']
                                    total_size += result['file_size']
                                    total_time += result.get('download_time', 0)
                                    
                                    # Log the speed
                                    speed_mbps = current_speed / (1024 * 1024)
                                    logger.info(f"Downloaded {result['file_name']} at {speed_mbps:.2f} MB/s")
                            else:
                                skipped += 1
                                
                            consecutive_errors = 0
                            results.append(True)  # Add a boolean True for success in results list
                        else:
                            error_count += 1
                            consecutive_errors += 1
                            results.append(False)  # Add a boolean False for failure in results list
                        
                        # Format speed for display
                        speed_text = ""
                        if current_speed > 0:
                            speed_mbps = current_speed / (1024 * 1024)
                            speed_text = f"{speed_mbps:.2f} MB/s"
                        
                        # Print a fancy progress bar with speed info
                        progress_bar = draw_fancy_progress_bar(completed_count, len(file_urls), 30, speed_text)
                        progress_text = f"Progress: {completed_count}/{len(file_urls)} files completed"
                        print(f"\n{format_text(progress_text, 'cyan')}\n{progress_bar}\n")
                        
                        # If we encounter too many consecutive errors, reduce concurrency
                        if consecutive_errors >= 3 and not reduced_concurrency:
                            reduced_workers = max(1, actual_workers // 2)
                            warning_msg = f"Too many consecutive errors, reducing concurrency to {reduced_workers} workers"
                            logger.warning(warning_msg)
                            print(f"\n{draw_box(warning_msg, title='Warning', color='yellow')}\n")
                            actual_workers = reduced_workers
                            reduced_concurrency = True
                            # Allow some time for the system to recover
                            time.sleep(3.0)
                        
                    except Exception as e:
                        error_msg = f"Error processing {url}: {str(e)}"
                        logger.error(error_msg)
                        print(f"\n{draw_box(error_msg, title='Download Error', color='red')}\n")
                        results.append(False)
                        error_count += 1
                        consecutive_errors += 1
                    
                    # Submit a new download task if there are URLs remaining and we haven't hit our concurrency limit
                    if remaining_urls and active_downloads < actual_workers:
                        next_url = remaining_urls.pop(0)
                        # Add a small delay between submitting new download tasks
                        time.sleep(CONCURRENT_DELAY)
                        futures_to_url[executor.submit(self._download_file, next_url, download_dir)] = next_url
                        active_downloads += 1
        
        # Check if all downloads were successful
        success_count = sum(1 for r in results if r)
        
        # Calculate aggregate statistics - with additional safety checks
        if total_time > 0.1:  # Ensure we have a meaningful amount of time
            avg_speed_mbps = (total_size / total_time) / (1024 * 1024)
            speed_stats = f"\nAverage download speed: {avg_speed_mbps:.2f} MB/s"
            total_size_mb = total_size / (1024 * 1024)
            size_stats = f"\nTotal downloaded: {total_size_mb:.2f} MB"
        else:
            speed_stats = ""
            size_stats = f"\nTotal downloaded: {total_size / (1024 * 1024):.2f} MB" if total_size > 0 else ""
        
        if skipped > 0:
            skipped_stats = f"\nFiles skipped (already downloaded): {skipped}"
        else:
            skipped_stats = ""
        
        # Create a final summary box with the results
        if error_count > 0:
            summary = (f"Files downloaded successfully: {success_count}/{len(file_urls)}\n"
                      f"Files with errors: {error_count}{skipped_stats}{size_stats}{speed_stats}")
            summary_box = draw_box(summary, title="Download Summary", color="yellow")
        else:
            summary = (f"All {len(file_urls)} files completed successfully!"
                      f"{skipped_stats}{size_stats}{speed_stats}")
            summary_box = draw_box(summary, title="Download Complete", color="green")
        
        print(f"\n{summary_box}\n")
        logger.info(f"Download complete: {success_count}/{len(file_urls)} files downloaded successfully")
        return error_count == 0  # Return true only if there were no errors
            
    def _download_files_sequentially(self, file_urls, download_dir):
        """
        Download multiple files sequentially one by one.
        
        Args:
            file_urls (list): List of file URLs to download
            download_dir (str): Directory to download files to
            
        Returns:
            bool: True if all files were downloaded successfully, False otherwise
        """
        if not file_urls:
            return True
            
        logger.info("Starting sequential downloads")
        
        # Create a header box for the download section
        header = draw_box(
            f"Total files: {len(file_urls)}\n"
            f"Download path: {os.path.abspath(download_dir)}\n"
            f"Mode: Sequential",
            title="Download Starting", color="blue", padding=1
        )
        print(f"\n{header}\n")
        
        results = []
        total_size = 0
        total_time = 0
        skipped = 0
        error_count = 0
        
        for i, url in enumerate(file_urls):
            # Create file info box for each download
            file_info = f"File {i+1}/{len(file_urls)}"
            file_box = draw_box(f"URL: {url}", title=file_info, color="cyan")
            print(f"\n{file_box}\n")
            
            logger.info(f"Downloading file {i+1}/{len(file_urls)}: {url}")
            result = self._download_file(url, download_dir)
            
            # Process download stats for progress display
            speed_text = ""
            if isinstance(result, dict) and result.get('success'):
                if not result.get('skipped', False):
                    if 'speed' in result and 'file_size' in result:
                        speed_mbps = result['speed'] / (1024 * 1024)  # Convert to MB/s
                        speed_text = f"{speed_mbps:.2f} MB/s"
                        total_size += result['file_size']
                        total_time += result.get('download_time', 0)
                else:
                    skipped += 1
                results.append(True)  # Add boolean True for success
            else:
                results.append(False)  # Add boolean False for failure
                error_count += 1
            
            # Print fancy progress bar after each download, with speed if available
            progress_bar = draw_fancy_progress_bar(i+1, len(file_urls), 30, speed_text)
            print(f"\n{format_text('Download Progress:', 'cyan')}\n{progress_bar}\n")
            
            # Add a small delay between downloads to avoid overwhelming the server
            if i < len(file_urls) - 1:  # No need to sleep after the last file
                sleep_with_random_delay(0.5, 1.0)
                # Add a separator line between downloads
                print(format_text('─' * 60, 'blue'))
        
        # Check if all downloads were successful
        success_count = sum(1 for r in results if r)
        
        # Calculate aggregate statistics - with additional safety checks
        if total_time > 0.1:  # Ensure we have a meaningful amount of time
            avg_speed_mbps = (total_size / total_time) / (1024 * 1024)
            speed_stats = f"\nAverage download speed: {avg_speed_mbps:.2f} MB/s"
            total_size_mb = total_size / (1024 * 1024)
            size_stats = f"\nTotal downloaded: {total_size_mb:.2f} MB"
        else:
            speed_stats = ""
            size_stats = f"\nTotal downloaded: {total_size / (1024 * 1024):.2f} MB" if total_size > 0 else ""
        
        if skipped > 0:
            skipped_stats = f"\nFiles skipped (already downloaded): {skipped}"
        else:
            skipped_stats = ""
        
        # Create a final summary box with the results
        if error_count > 0:
            summary = (f"Files downloaded successfully: {success_count}/{len(file_urls)}\n"
                      f"Files with errors: {error_count}"
                      f"{skipped_stats}{size_stats}{speed_stats}")
            summary_box = draw_box(summary, title="Download Summary", color="yellow")
        else:
            summary = (f"All {len(file_urls)} files completed successfully!"
                      f"{skipped_stats}{size_stats}{speed_stats}")
            summary_box = draw_box(summary, title="Download Complete", color="green")
            
        print(f"\n{summary_box}\n")
        logger.info(f"Download complete: {success_count}/{len(file_urls)} files downloaded successfully")
        return error_count == 0  # Return true only if there were no errors
            
    def _download_file(self, file_url, download_dir=None):
        """
        Download a single file.
        
        Args:
            file_url (str): URL of the file to download
            download_dir (str, optional): Directory to download the file to
            
        Returns:
            dict or bool: Dict with download stats if successful, False otherwise
        """
        try:
            # Prepare download path
            download_path = get_and_prepare_download_path(download_dir, None)
            
            # Check if already downloaded
            already_downloaded = get_already_downloaded_url(download_path)
            if file_url in already_downloaded:
                msg = f"Skipping already downloaded: {file_url}"
                logger.info(msg)
                print(f"\n{draw_box(msg, title='Skipped', color='blue')}\n")
                # Return a minimal successful result without speed
                return {'success': True, 'skipped': True} 
                
            # Get the appropriate downloader
            downloader = DownloaderFactory.get_downloader(file_url, self.session, self.proxy_url)
            
            # Get the real download URL
            logger.info(f"Getting download URL for: {file_url}")
            print(f"{format_text('Retrieving download URL...', 'cyan')}")
            
            download_info = downloader.get_real_download_url(file_url)
            
            if not download_info:
                error_msg = f"Failed to get download URL for: {file_url}"
                logger.error(error_msg)
                print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
                return False
                
            # Download the file
            print(f"{format_text('Starting download...', 'cyan')}")
            result = downloader.download_with_retry(
                download_info["url"], 
                download_path
            )
            
            # If download was successful, add to already downloaded list
            if isinstance(result, dict) and result.get('success', False):
                # Format speed for display if available
                if 'speed' in result:
                    speed_mbps = result['speed'] / (1024 * 1024)  # Convert to MB/s
                    file_size_mb = result['file_size'] / (1024 * 1024)  # Convert to MB
                    print(f"{format_text('Download completed:', 'green')} {file_size_mb:.2f} MB at {speed_mbps:.2f} MB/s")
                    result['formatted_speed'] = f"{speed_mbps:.2f} MB/s"
                
                return result
            elif result is True:  # Handle legacy boolean return
                from .utils.file_utils import mark_as_downloaded
                mark_as_downloaded(file_url, download_path)
                return {'success': True}
            else:
                return False
                
        except Exception as e:
            error_msg = f"Error downloading file {file_url}: {str(e)}"
            logger.error(error_msg)
            print(f"\n{draw_box(error_msg, title='Error', color='red')}\n")
            return False