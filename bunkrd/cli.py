"""
Command-line interface for the BunkrDownloader application.
"""
import argparse
import sys
import logging
import textwrap
import shutil
import os
from .controller import DownloadController
from .config import (
    ERROR_MESSAGES, DEFAULT_PROXY, RESPECT_ROBOTS_TXT, 
    DEFAULT_DOWNLOAD_PATH
)

# ANSI color codes for terminal output
COLORS = {
    'reset': '\033[0m',
    'bold': '\033[1m',
    'green': '\033[32m',
    'red': '\033[31m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m',
    'bg_black': '\033[40m',
    'bg_blue': '\033[44m',
    'bg_cyan': '\033[46m',
    'bg_green': '\033[42m',
}

# Box drawing characters for better visual formatting
BOX_CHARS = {
    'top_left': '┌',
    'top_right': '┐',
    'bottom_left': '└',
    'bottom_right': '┘',
    'horizontal': '─',
    'vertical': '│',
    'title_left': '┤',
    'title_right': '├',
    'progress_bar': '█',
    'progress_empty': '░',
}

def draw_box(text, width=None, title=None, color='cyan', padding=1):
    """Draw a fancy box around text with optional title."""
    if width is None:
        lines = text.split('\n')
        width = max(len(line) for line in lines) + (padding * 2)
    
    if title:
        title = f" {title} "
        title_width = min(len(title) + 4, width - 4)  # Ensure title fits
    
    result = []
    
    # Top border with optional title
    if title:
        title_padding = (width - title_width) // 2
        top = (f"{COLORS[color]}{BOX_CHARS['top_left']}" +
               f"{BOX_CHARS['horizontal'] * title_padding}" +
               f"{BOX_CHARS['title_left']}{COLORS['bold']}{title}{COLORS['reset']}{COLORS[color]}{BOX_CHARS['title_right']}" +
               f"{BOX_CHARS['horizontal'] * (width - title_width - title_padding - 2)}" +
               f"{BOX_CHARS['top_right']}{COLORS['reset']}")
    else:
        top = f"{COLORS[color]}{BOX_CHARS['top_left']}{BOX_CHARS['horizontal'] * width}{BOX_CHARS['top_right']}{COLORS['reset']}"
    
    result.append(top)
    
    # Add text with padding
    for line in text.split('\n'):
        padded_line = line + ' ' * (width - len(line) - (padding * 2))
        result.append(f"{COLORS[color]}{BOX_CHARS['vertical']}{' ' * padding}{padded_line}{' ' * padding}{BOX_CHARS['vertical']}{COLORS['reset']}")
    
    # Bottom border
    bottom = f"{COLORS[color]}{BOX_CHARS['bottom_left']}{BOX_CHARS['horizontal'] * width}{BOX_CHARS['bottom_right']}{COLORS['reset']}"
    result.append(bottom)
    
    return '\n'.join(result)

def format_text(text, color=None, bold=False):
    """Format text with ANSI color codes if supported by terminal."""
    if sys.platform == 'win32':
        # Check if Windows terminal supports ANSI colors
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            # If not supported, return plain text
            return text
    
    result = ""
    if bold:
        result += COLORS['bold']
    if color and color in COLORS:
        result += COLORS[color]
    
    result += text + COLORS['reset']
    return result

def draw_fancy_progress_bar(current, total, width=30):
    """Draw a fancy progress bar with percentage."""
    progress = int(width * current / total) if total > 0 else 0
    percentage = f"{current / total * 100:.1f}%" if total > 0 else "0.0%"
    
    bar = (f"{COLORS['cyan']}{BOX_CHARS['progress_bar'] * progress}"
           f"{COLORS['reset']}{BOX_CHARS['progress_empty'] * (width - progress)}")
    
    return f"[{bar}] {percentage} ({current}/{total})"

def configure_logging(verbosity):
    """
    Configure logging to write to a file instead of the console.
    
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
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure file handler for logging
    log_file = os.path.join(log_dir, 'bunkr_downloader.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    
    # Set formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Configure root logger to use the file handler instead of console
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove any existing handlers (including console handlers)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Add the file handler
    root_logger.addHandler(file_handler)
    
    return level

def parse_arguments():
    """
    Parse command-line arguments with a cleaner, more organized interface.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    # Create a parser with a nicer description and epilog
    parser = argparse.ArgumentParser(
        description=format_text('BunkrDownloader: Download files from Bunkr and Cyberdrop', 'cyan', True),
        epilog=textwrap.dedent(f'''
        {format_text('Examples:', 'green', True)}
          bunkrd -u https://bunkr.sk/a/example-album -o ./downloads
          bunkrd -f url_list.txt -o ./downloads
          bunkrd -i -o ./downloads --proxy socks5://127.0.0.1:9050
        '''),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Group 1: Input Methods (mutually exclusive)
    input_group = parser.add_argument_group(format_text('Input Options', 'blue', True))
    input_source = input_group.add_mutually_exclusive_group()
    input_source.add_argument(
        '-u', '--url', 
        help='URL to download from'
    )
    input_source.add_argument(
        '-f', '--file', 
        help='File containing URLs to download (one URL per line)'
    )
    input_source.add_argument(
        '-i', '--interactive', 
        action='store_true',
        help='Run in interactive mode to enter URLs during execution'
    )
    
    # Group 2: Output Options
    output_group = parser.add_argument_group(format_text('Output Options', 'blue', True))
    output_group.add_argument(
        '-o', '--output', 
        help=f'Directory to save files to (default: {DEFAULT_DOWNLOAD_PATH})',
        default=DEFAULT_DOWNLOAD_PATH
    )
    
    # Group 3: Network Options
    network_group = parser.add_argument_group(format_text('Network Options', 'blue', True))
    network_group.add_argument(
        '--proxy', 
        help='Use a proxy for requests (e.g., socks5://127.0.0.1:9050)'
    )
    network_group.add_argument(
        '--no-robots-check', 
        action='store_true',
        help='Disable robots.txt compliance checking'
    )
    network_group.add_argument(
        '--min-delay', 
        type=float,
        help='Minimum delay between requests in seconds (default: 1.0)'
    )
    network_group.add_argument(
        '--max-delay', 
        type=float,
        help='Maximum delay between requests in seconds (default: 3.0)'
    )
    network_group.add_argument(
        '--concurrent-downloads', 
        action='store_true',
        help='Enable concurrent downloads instead of sequential downloads'
    )
    network_group.add_argument(
        '--concurrent', 
        type=int,
        help='Maximum concurrent downloads (default: 3, only used with --concurrent-downloads)'
    )
    
    # Group 4: Logging Options
    logging_group = parser.add_argument_group(format_text('Logging Options', 'blue', True))
    verbosity = logging_group.add_mutually_exclusive_group()
    verbosity.add_argument(
        '-v', '--verbose',
        action='count',
        default=1,
        help='Increase output verbosity (can be used multiple times, e.g. -vvv)'
    )
    verbosity.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress all output except errors'
    )
    
    return parser.parse_args()

def display_banner():
    """Display a nice banner when the program starts."""
    # Get terminal width
    terminal_width = shutil.get_terminal_size().columns
    
    # Banner content
    app_name = "Bunkrd"
    app_desc = "A tool to download files from Bunkr & Cyberdrop"
    version = "v1.0.0"
    
    # Create the banner
    banner_content = f"{app_name} {version}\n{app_desc}"
    banner = draw_box(banner_content, title="Welcome", color="cyan", padding=2)
    
    # Calculate padding for centering in terminal
    banner_width = len(banner.split('\n')[0])
    left_padding = (terminal_width - banner_width) // 2
    padding = " " * max(0, left_padding)
    
    # Add padding to each line
    banner = '\n'.join(f"{padding}{line}" for line in banner.split('\n'))
    
    print(f"\n{banner}\n")

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
    
    # Display interactive mode header
    header = draw_box("Enter URLs to download (one per line)\nType 'exit', 'quit', or press Ctrl+C to exit", 
                    title="Interactive Mode", color="blue", padding=2)
    print(f"\n{header}\n")
    
    successes = 0
    failures = 0
    
    try:
        while True:
            try:
                # Get URL from user with a nicer prompt
                url = input(f"{format_text('URL', 'green', True)} > ").strip()
                
                # Check for exit command
                if url.lower() in ('exit', 'quit', 'q'):
                    break
                
                # Skip empty lines
                if not url:
                    continue
                    
                # Process the URL
                print(f"\n{format_text('Processing:', 'cyan')} {format_text(url, 'yellow')}")
                print(f"{format_text('─' * (len(url) + 12), 'cyan')}")
                
                if controller.process_url(url, download_dir):
                    success_msg = draw_box("Download completed successfully", title="Success", color="green")
                    print(f"\n{success_msg}")
                    successes += 1
                else:
                    error_msg = draw_box("Download failed", title="Error", color="red")
                    print(f"\n{error_msg}")
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
        summary = (f"Downloads: {successes}/{total} completed successfully\n"
                  f"Success rate: {(successes/total)*100:.1f}%")
        
        summary_box = draw_box(summary, title="Summary", 
                             color="green" if failures == 0 else "yellow")
        print(f"\n{summary_box}\n")
        
    return 0 if failures == 0 else 1

def main():
    """Main entry point for the command-line interface."""
    try:
        # Display banner at start
        display_banner()
        
        args = parse_arguments()
        
        # Set verbosity level (quiet mode overrides verbose)
        verbosity = 0 if args.quiet else args.verbose
        log_level = configure_logging(verbosity)
        
        logger = logging.getLogger(__name__)
        
        # Check that at least one input method was provided
        if not (args.url or args.file or args.interactive):
            print(f"{format_text('Error:', 'red', True)} No input method specified.")
            print("Use -u/--url, -f/--file, or -i/--interactive")
            return 1
            
        # Configure proxy settings
        proxy_url = args.proxy if args.proxy else DEFAULT_PROXY
        
        # Create controller with configured settings
        controller = DownloadController(
            proxy_url=proxy_url,
            max_concurrent_downloads=args.concurrent if args.concurrent_downloads else 1,
            log_level=log_level
        )
        
        # Process based on the provided input method
        if args.interactive:
            return interactive_mode(controller, args.output)
        elif args.url:
            print(f"Processing URL: {format_text(args.url, 'yellow')}")
            success = controller.process_url(args.url, args.output)
        elif args.file:
            print(f"Processing URLs from file: {format_text(args.file, 'yellow')}")
            success = controller.process_file(args.file, args.output)
        else:
            # This case is now handled by the earlier check
            pass
            
        if success:
            print(f"{format_text('✓ Processing completed successfully', 'green')}")
            return 0
        else:
            print(f"{format_text('✗ Processing completed with errors', 'red')}")
            return 1
            
    except KeyboardInterrupt:
        print(f"\n{format_text('Operation interrupted by user', 'yellow')}")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())