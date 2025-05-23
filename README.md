# BunkrDownloader

A command-line tool to download files from Bunkr and Cyberdrop.

## Features

- Download individual files or entire albums from Bunkr and Cyberdrop
- Track already downloaded files to avoid re-downloading
- Track failed downloads to prevent repeated attempts on problematic files
- Display download speed metrics in real-time and summary statistics
- Automatically create directories based on album names
- Support for both direct file URLs and album URLs
- Error handling and retry mechanism
- Proxy support for anonymous downloads
- Rate limiting to avoid IP bans
- Sequential downloads by default for better stability
- Dynamic concurrent downloads with automatic thread scaling based on system resources
- Intelligent memory and CPU usage monitoring to optimize performance
- Incremental HTML parsing for handling extremely large album pages with minimal memory usage
- Configurable delay between downloads to avoid rate limiting

## Installation

### Option 1: Install from source

```bash
git clone https://github.com/yourusername/bunkrDownloader.git
cd bunkrDownloader
pip install -e .
```

### Option 2: Direct execution

```bash
git clone https://github.com/yourusername/bunkrDownloader.git
cd bunkrDownloader
pip install -r requirements.txt
```

## Usage

### Command-line options

```
usage: bunkrd [-h] [-u URL | -f FILE | -i] [-o OUTPUT] [--proxy PROXY]
                      [--no-robots-check] [--min-delay MIN_DELAY] [--max-delay MAX_DELAY]
                      [--concurrent-downloads] [--concurrent CONCURRENT] [-v] [-q]

Download files from Bunkr and Cyberdrop.

optional arguments:
  -h, --help            show this help message and exit
  -u URL, --url URL     URL to download from
  -f FILE, --file FILE  File containing URLs to download
  -i, --interactive     Run in interactive mode
  -o OUTPUT, --output OUTPUT
                        Directory to save files to
  --proxy PROXY         Use a proxy for requests (e.g., socks5://127.0.0.1:9050)
  --no-robots-check     Disable robots.txt compliance checking
  --min-delay MIN_DELAY
                        Minimum delay between requests in seconds (default: 1.0)
  --max-delay MAX_DELAY
                        Maximum delay between requests in seconds (default: 3.0)
  --concurrent-downloads
                        Enable concurrent downloads instead of sequential downloads
  --concurrent CONCURRENT
                        Maximum concurrent downloads (default: 3, only used with --concurrent-downloads)
  -v, --verbose         Increase output verbosity (can be used multiple times, e.g. -vvv)
  -q, --quiet           Suppress all output except errors
```

### Examples

#### Download from a single URL (sequential download)

```bash
bunkrd -u https://bunkr.sk/a/example-album -o ./downloads
```

#### Download from a single URL with concurrent downloads

```bash
bunkrd -u https://bunkr.sk/a/example-album -o ./downloads --concurrent-downloads
```

#### Download from multiple URLs in a file

```bash
bunkrd -f url_list.txt -o ./downloads
```

#### Interactive mode

```bash
bunkrd -i -o ./downloads
```

#### Using a proxy with concurrent downloads and custom thread count

```bash
bunkrd -u https://bunkr.sk/a/example-album --proxy socks5://127.0.0.1:9050 --concurrent-downloads --concurrent 5
```

#### Using the original script name (for backward compatibility)

```bash
python dump.py -u https://bunkr.sk/a/example-album -o ./downloads
```

## Smart Download Handling

### Download Speed Display

The tool shows real-time download speed information:

- Individual file progress bars display current speed in MB/s
- After completing all downloads, summary information shows:
  - Total downloaded data size
  - Average download speed across all files
  - Number of files skipped (already downloaded)

### Dynamic Thread Scaling

The concurrent download feature now includes intelligent thread scaling:

- Automatically determines optimal number of threads based on:
  - Available CPU cores and current system load
  - Memory usage and availability
  - Network performance and connection speed
  - Download success rates and error patterns
- Dynamically adjusts thread count during downloads:
  - Increases threads on powerful machines with fast connections
  - Reduces threads when system resources are constrained
  - Scales down when errors or timeouts are detected
  - Provides real-time feedback about thread adjustments
- Benefits of dynamic scaling:
  - Better performance on high-end systems
  - More reliable downloads on resource-constrained devices
  - Automatic adaptation to changing network conditions
  - Improved success rates by reducing concurrency when needed

### Failed Download Tracking

To prevent the tool from repeatedly attempting to download problematic files:

- Failed downloads are marked with a `[FAILED]` tag in the `already_downloaded.txt` file
- When running the tool again, these files will be skipped with a "Skipped (Failed Previously)" message
- To retry downloading a failed file, simply remove its entry from the `already_downloaded.txt` file

### Incremental HTML Parser

The application now uses an incremental HTML parser for album pages, which offers significant benefits:

- **Memory Efficiency**: Processes HTML content in chunks (8KB by default) rather than loading the entire page into memory
- **Large Album Support**: Handles extremely large albums (1000+ files) without running out of memory
- **Progressive Processing**: Extracts file URLs as they're found rather than waiting for the entire page to load
- **Reliable Operation**: Can recover partial results even if parsing is interrupted due to network errors
- **Real-time Progress**: Shows file discovery progress during parsing for better feedback

This feature is especially valuable when downloading from albums containing hundreds or thousands of files, as it allows the application to run smoothly even on systems with limited RAM.

## Testing

The project includes a comprehensive test suite to ensure functionality. Unit tests cover individual components, while mocks are used to avoid real network requests during testing.

### Running Tests

To run all tests:

```bash
python run_tests.py
```

For more verbose output:

```bash
python run_tests.py -v
```

### Test Structure

- `tests/unit/`: Unit tests for individual components
  - `downloaders/`: Tests for downloader implementations
  - `parsers/`: Tests for parser implementations
  - `utils/`: Tests for utility functions
- `tests/mock_services.py`: Mocks for external services

### Writing New Tests

When contributing new features, please add appropriate tests:

1. Unit tests for new functions/classes
2. Update mock services if needed to simulate APIs
3. Ensure all tests pass before submitting a pull request

## Project Structure

```
bunkrDownloader/
├── bunkrd/
│   ├── __init__.py       # Package initialization
│   ├── cli.py            # Command-line interface
│   ├── config.py         # Configuration settings
│   ├── controller.py     # Main download controller
│   ├── downloaders/      # Downloader implementations
│   │   ├── __init__.py
│   │   ├── base_downloader.py  # Base downloader class
│   │   ├── bunkr_downloader.py # Bunkr implementation
│   │   ├── cyberdrop_downloader.py # Cyberdrop implementation
│   │   └── factory.py    # Factory to create appropriate downloader
│   ├── parsers/          # Parser implementations
│   │   ├── __init__.py
│   │   ├── bunkr_parser.py
│   │   ├── cyberdrop_parser.py
│   │   └── factory.py    # Factory to create appropriate parser
│   └── utils/            # Utility functions
│       ├── __init__.py
│       ├── file_utils.py # File handling utilities
│       ├── request_utils.py # Network request utilities
│       └── security_utils.py # Security and encryption utilities
├── tests/                # Test suite
│   ├── __init__.py
│   ├── mock_services.py  # Mock services for testing
│   ├── unit/             # Unit tests
│   │   ├── downloaders/  # Tests for downloaders
│   │   ├── parsers/      # Tests for parsers
│   │   └── utils/        # Tests for utilities
│   └── integration/      # Integration tests
├── run_tests.py          # Test runner script
├── dump.py               # Original entry point (for backward compatibility)
├── setup.py              # Package setup script
└── requirements.txt      # Dependencies
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests covering your changes
4. Implement your feature or fix
5. Make sure all tests pass (`python run_tests.py`)
6. Commit your changes (`git commit -m 'Add some amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Create a Pull Request

### Contribution Guidelines

- Follow PEP 8 coding style
- Write docstrings for all functions, classes, and modules
- Add appropriate error handling
- Include unit tests for new functionality
- Update documentation as needed

## License

This project is licensed under the MIT License.
