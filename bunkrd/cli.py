"""
Command-line interface for the BunkrDownloader application.
"""
import argparse
import sys
import logging
from .controller import DownloadController
from .config import (
    ERROR_MESSAGES, DEFAULT_PROXY, RESPECT_ROBOTS_TXT, 
    DEFAULT_DOWNLOAD_PATH
)

def configure_logging(verbosity):
    """
    Configure logging level based on verbosity.
    
    Args:
        verbosity (int): Verbosity level (0-3)
        
    Returns:
        int: The configured logging level
    """
    # Set up logging levels based on verbosity
    if verbosity == 0:
        level = logging.ERROR  # Only errors
    elif verbosity == 1:
        level = logging.WARNING  # Errors and warnings
    elif verbosity == 2:
        level = logging.INFO  # Errors, warnings, and info
    else:
        level = logging.DEBUG  # Everything including debug info
        
    # Configure root logger (affects all loggers)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # Log to console
        ]
    )
    
    return level

def parse_arguments():
    """
    Parse command-line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Download files from Bunkr and Cyberdrop.')
    
    # Group URL and file as mutually exclusive options, but both are now optional
    # to support interactive mode
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('-u', '--url', help='URL to download from')
    input_group.add_argument('-f', '--file', help='File containing URLs to download')
    input_group.add_argument('-i', '--interactive', action='store_true', 
                          help='Run in interactive mode, allowing URLs to be entered during execution')
    
    parser.add_argument('-o', '--output', help='Directory to save files to',
                      default=DEFAULT_DOWNLOAD_PATH)
    
    # Anti-detection features
    parser.add_argument('--proxy', help='Use a proxy for requests (e.g., socks5://127.0.0.1:9050)')
    parser.add_argument('--no-robots-check', action='store_true', 
                      help='Disable robots.txt compliance checking')
    parser.add_argument('--min-delay', type=float,
                      help='Minimum delay between requests in seconds (default: 1.0)')
    parser.add_argument('--max-delay', type=float,
                      help='Maximum delay between requests in seconds (default: 3.0)')
    parser.add_argument('--concurrent', type=int,
                      help='Maximum concurrent downloads (default: 3)')
                      
    # Logging options
    parser.add_argument('-v', '--verbose', action='count', default=1,
                      help='Increase output verbosity (can be used multiple times, e.g. -vvv)')
    parser.add_argument('-q', '--quiet', action='store_true',
                      help='Suppress all output except errors')
                      
    return parser.parse_args()

def interactive_mode(controller, download_dir):
    """
    Run the application in interactive mode, prompting for URLs.
    
    Args:
        controller (DownloadController): The download controller instance
        download_dir (str): Directory to save files to
        
    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    logger = logging.getLogger(__name__)
    print("\nBunkrDownloader Interactive Mode")
    print("===============================")
    print("Enter URLs to download (one per line).")
    print("Type 'exit', 'quit', or press Ctrl+C to exit.")
    print("")
    
    successes = 0
    failures = 0
    
    try:
        while True:
            try:
                # Get URL from user
                url = input("Enter URL (or exit/quit): ").strip()
                
                # Check for exit command
                if url.lower() in ('exit', 'quit', 'q'):
                    break
                
                # Skip empty lines
                if not url:
                    continue
                    
                # Process the URL
                print(f"\nProcessing URL: {url}")
                if controller.process_url(url, download_dir):
                    print("✓ Download completed successfully")
                    successes += 1
                else:
                    print("✗ Download failed")
                    failures += 1
                print("")  # Add blank line between downloads
                
            except KeyboardInterrupt:
                # Allow Ctrl+C to exit the inner loop and show stats
                break
                
    except KeyboardInterrupt:
        # Catch outer Ctrl+C
        print("\n\nInterrupted by user.")
    
    # Show summary
    total = successes + failures
    if total > 0:
        print(f"\nSummary: {successes}/{total} downloads completed successfully")
        
    return 0 if failures == 0 else 1

def main():
    """Main entry point for the command-line interface."""
    try:
        args = parse_arguments()
        
        # Set verbosity level (quiet mode overrides verbose)
        verbosity = 0 if args.quiet else args.verbose
        log_level = configure_logging(verbosity)
        
        logger = logging.getLogger(__name__)
        
        # Check that at least one input method was provided
        if not (args.url or args.file or args.interactive):
            logger.error(ERROR_MESSAGES.get('no_input_method', 
                       "No input method specified. Use -u/--url, -f/--file, or -i/--interactive"))
            return 1
            
        # Configure proxy settings
        proxy_url = args.proxy if args.proxy else DEFAULT_PROXY
        
        # Create controller with configured settings
        controller = DownloadController(
            proxy_url=proxy_url,
            max_concurrent_downloads=args.concurrent,
            log_level=log_level
        )
        
        # Process based on the provided input method
        if args.interactive:
            return interactive_mode(controller, args.output)
        elif args.url:
            logger.info(f"Processing URL: {args.url}")
            success = controller.process_url(args.url, args.output)
        elif args.file:
            logger.info(f"Processing URLs from file: {args.file}")
            success = controller.process_file(args.file, args.output)
        else:
            # This case is now handled by the earlier check
            pass
            
        if success:
            logger.info("Processing completed successfully")
            return 0
        else:
            logger.error("Processing completed with errors")
            return 1
            
    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())