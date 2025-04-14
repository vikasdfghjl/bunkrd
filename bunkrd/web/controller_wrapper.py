"""
Controller wrapper for web UI integration.

This module provides a wrapper around the DownloadController class
to better integrate with the web interface by reporting progress.
"""

from ..controller import DownloadController
import time
import logging
import os

# Set up logger
logger = logging.getLogger(__name__)


class WebUIController:
    """
    Wrapper for DownloadController that reports progress to the web UI.
    """
    
    def __init__(self, progress_tracker, proxy_url=None, max_concurrent_downloads=None, 
                 min_delay=None, max_delay=None, respect_robots_txt=True):
        """
        Initialize the web UI controller wrapper.
        
        Args:
            progress_tracker: WebProgressTracker instance for reporting progress
            proxy_url (str, optional): Proxy URL to use
            max_concurrent_downloads (int, optional): Maximum number of concurrent downloads
            min_delay (float, optional): Minimum delay between requests in seconds
            max_delay (float, optional): Maximum delay between requests in seconds
            respect_robots_txt (bool, optional): Whether to respect robots.txt rules
        """
        self.tracker = progress_tracker
        self.controller = DownloadController(
            proxy_url=proxy_url,
            max_concurrent_downloads=max_concurrent_downloads
        )
        
        # Configure additional settings if provided
        from ..config import MIN_REQUEST_DELAY, MAX_REQUEST_DELAY
        
        # Update request delay settings if provided
        if min_delay is not None:
            from ..utils.request_utils import MIN_REQUEST_DELAY as MIN_DELAY_REF
            import builtins
            builtins.MIN_REQUEST_DELAY = min_delay
            
        if max_delay is not None:
            from ..utils.request_utils import MAX_REQUEST_DELAY as MAX_DELAY_REF
            import builtins
            builtins.MAX_REQUEST_DELAY = max_delay
        
        # Update robots.txt compliance setting if provided
        import builtins
        from ..config import RESPECT_ROBOTS_TXT as ROBOTS_REF
        builtins.RESPECT_ROBOTS_TXT = respect_robots_txt
        
        # Store original methods before monkey patching
        self.original_download_files_sequentially = self.controller._download_files_sequentially
        self.original_download_files_concurrently = self.controller._download_files_concurrently
        self.original_process_album = self.controller._process_album
        self.original_download_file = None
        
        # Try to get the actual download_file method from controller or downloader
        if hasattr(self.controller, 'download_file'):
            self.original_download_file = self.controller.download_file
        elif hasattr(self.controller, '_download_file'):
            self.original_download_file = self.controller._download_file
        
        # Monkey patch controller methods to track progress
        self.patch_controller_methods()
    
    def patch_controller_methods(self):
        """Monkey patch controller methods to report progress."""
        original_self = self
        
        def wrapped_download_sequentially(controller_self, file_urls, download_dir):
            """Wrap the sequential downloader to report progress."""
            if not file_urls:
                return True
            
            # Update tracker with total files
            original_self.tracker.update_album_progress(len(file_urls), 0)
            
            # Initialize all files as queued
            for url in file_urls:
                filename = os.path.basename(url)
                original_self.tracker.update_file_status(filename, "queued")
            
            completed_count = 0
            success = True
            
            for file_url in file_urls:
                try:
                    filename = os.path.basename(file_url)
                    
                    # Update current file status to downloading
                    original_self.tracker.update_file_status(filename, "downloading")
                    original_self.tracker.update_album_progress(len(file_urls), completed_count, filename)
                    
                    # Download the file using controller's method
                    from ..downloaders.base_downloader import BaseDownloader
                    downloader = BaseDownloader(controller_self.session, controller_self.proxy_url)
                    
                    # Create a wrapper for the download to track progress
                    def progress_callback(downloaded_bytes, total_bytes):
                        if total_bytes > 0:
                            progress_percent = int((downloaded_bytes / total_bytes) * 100)
                        else:
                            progress_percent = 0
                        original_self.tracker.update_file_progress(filename, progress_percent, total_bytes)
                    
                    # Download file with progress tracking
                    result = downloader.download_file(file_url, download_dir, progress_callback)
                    
                    if result:
                        original_self.tracker.update_file_status(filename, "completed")
                        completed_count += 1
                    else:
                        original_self.tracker.update_file_status(filename, "failed")
                        success = False
                    
                    # Update overall progress
                    original_self.tracker.update_album_progress(len(file_urls), completed_count)
                    
                except Exception as e:
                    logger.exception(f"Error downloading file {file_url}: {str(e)}")
                    original_self.tracker.update_file_status(filename, "failed")
                    success = False
            
            # Update tracker with final status
            final_message = f"Completed {completed_count} of {len(file_urls)} files"
            if success:
                original_self.tracker.update_status('completed', final_message)
            else:
                original_self.tracker.update_status('failed', final_message)
            
            return success
        
        def wrapped_download_concurrently(controller_self, file_urls, download_dir):
            """Wrap the concurrent downloader to report progress."""
            if not file_urls:
                return True
                
            # Update tracker with total files
            original_self.tracker.update_album_progress(len(file_urls), 0)
            original_self.tracker.update_status('processing', f"Downloading {len(file_urls)} files concurrently")
            
            # Initialize all files as queued
            for url in file_urls:
                filename = os.path.basename(url)
                original_self.tracker.update_file_status(filename, "queued")
            
            # We need to create a custom wrapper for the concurrent download
            # Since we'll need to intercept the callback functions
            
            # Record which files have been downloaded
            completed_files = []
            failed_files = []
            
            # Create a function to update progress when a download completes
            def download_complete_callback(url, success):
                filename = os.path.basename(url)
                if success:
                    original_self.tracker.update_file_status(filename, "completed")
                    completed_files.append(url)
                else:
                    original_self.tracker.update_file_status(filename, "failed")
                    failed_files.append(url)
                
                # Update overall progress
                original_self.tracker.update_album_progress(
                    len(file_urls), 
                    len(completed_files)
                )
            
            # Try to patch the concurrent download method to track progress
            try:
                # Save the original method
                original_concurrent_method = controller_self._download_files_concurrently
                
                # Call the original method
                result = original_concurrent_method(file_urls, download_dir)
                
                # Update tracker with final status based on number of completed files
                completed_count = len([f for f in file_urls if os.path.exists(os.path.join(download_dir, os.path.basename(f)))])
                
                # Update overall progress
                original_self.tracker.update_album_progress(len(file_urls), completed_count)
                
                # Update final status
                final_message = f"Completed {completed_count} of {len(file_urls)} files"
                if result:
                    original_self.tracker.update_status('completed', final_message)
                else:
                    original_self.tracker.update_status('failed', final_message)
                
                return result
            
            except Exception as e:
                logger.exception(f"Error in concurrent download: {str(e)}")
                original_self.tracker.update_status('failed', f"Error in concurrent download: {str(e)}")
                return False
        
        def wrapped_process_album(controller_self, album_url, download_dir=None):
            """Wrap the album processing method to report progress."""
            try:
                # Update status
                original_self.tracker.update_status('processing', f"Parsing album: {album_url}")
                
                # Create a temporary wrapper for internal album processing
                # Store the current wrapper methods
                temp_sequential = controller_self._download_files_sequentially
                temp_concurrent = controller_self._download_files_concurrently
                
                # Restore original methods temporarily to avoid recursion
                controller_self._download_files_sequentially = original_self.original_download_files_sequentially
                controller_self._download_files_concurrently = original_self.original_download_files_concurrently
                
                # Get the appropriate parser
                parser = controller_self._get_parser(album_url)
                
                # Parse the album
                album_data = parser.parse_album(album_url)
                
                if not album_data["files"]:
                    original_self.tracker.update_status('failed', f"No files found in album: {album_url}")
                    return False
                
                # Update with album info
                original_self.tracker.update_status(
                    'processing', 
                    f"Found {len(album_data['files'])} files in album: {album_data['album_name']}"
                )
                
                # Restore wrapped methods before calling album processing
                controller_self._download_files_sequentially = temp_sequential
                controller_self._download_files_concurrently = temp_concurrent
                
                # Call the original method to handle the actual album processing
                result = original_self.original_process_album(album_url, download_dir)
                
                return result
            except Exception as e:
                original_self.tracker.update_status('error', f"Error processing album: {str(e)}")
                logger.exception(f"Error in wrapped_process_album: {str(e)}")
                return False
                
        # Create a method to get parser since it's used in our wrapper
        def get_parser(controller_self, url):
            try:
                # Import locally to avoid circular imports
                from ..parsers.factory import ParserFactory
                return ParserFactory.get_parser(url, controller_self.session, controller_self.proxy_url)
            except Exception as e:
                logger.exception(f"Error getting parser: {str(e)}")
                # Try using controller's internal method if available
                if hasattr(controller_self, '_get_parser'):
                    return controller_self._get_parser(url)
                raise
            
        # Apply patches
        self.controller._download_files_sequentially = lambda file_urls, download_dir: wrapped_download_sequentially(self.controller, file_urls, download_dir)
        self.controller._download_files_concurrently = lambda file_urls, download_dir: wrapped_download_concurrently(self.controller, file_urls, download_dir)
        self.controller._process_album = lambda album_url, download_dir=None: wrapped_process_album(self.controller, album_url, download_dir)
        self.controller._get_parser = lambda url: get_parser(self.controller, url)
        
    def process_url(self, url, download_dir=None):
        """
        Process a URL using the wrapped controller.
        
        Args:
            url (str): URL to process
            download_dir (str, optional): Directory to download files to
            
        Returns:
            bool: True if processing was successful, False otherwise
        """
        self.tracker.update_status('processing', f"Processing URL: {url}")
        
        try:
            result = self.controller.process_url(url, download_dir)
            return result
        except Exception as e:
            self.tracker.update_status('error', f"Error processing URL: {str(e)}")
            logger.exception(f"Error in process_url: {str(e)}")
            return False
            
    def process_file(self, file_path, download_dir=None):
        """
        Process URLs from a file using the wrapped controller.
        
        Args:
            file_path (str): Path to file containing URLs
            download_dir (str, optional): Directory to download files to
            
        Returns:
            bool: True if all URLs were processed successfully, False otherwise
        """
        self.tracker.update_status('processing', f"Processing URLs from file: {file_path}")
        
        try:
            result = self.controller.process_file(file_path, download_dir)
            return result
        except Exception as e:
            self.tracker.update_status('error', f"Error processing file: {str(e)}")
            logger.exception(f"Error in process_file: {str(e)}")
            return False