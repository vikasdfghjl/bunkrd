#!/bin/bash
set -e

# Function to display help
show_help() {
    echo "BunkrDownloader Docker Container"
    echo ""
    echo "Usage:"
    echo "  docker run [docker-options] bunkrdownloader [options]"
    echo ""
    echo "Examples:"
    echo "  # Run with a URL"
    echo "  docker run -v /path/to/downloads:/data/downloads bunkrdownloader -u https://bunkr.sk/a/example"
    echo ""
    echo "  # Show help"
    echo "  docker run bunkrdownloader --help"
    echo ""
}

# Function to make sure needed directories exist
ensure_dirs() {
    mkdir -p "$BUNKR_DOWNLOAD_DIR"
    mkdir -p "$BUNKR_LOG_DIR"
    chmod -R 777 "$BUNKR_DOWNLOAD_DIR" || true
    chmod -R 777 "$BUNKR_LOG_DIR" || true
    echo "Directories created/verified:"
    echo "- Download directory: $BUNKR_DOWNLOAD_DIR"
    echo "- Log directory: $BUNKR_LOG_DIR"
}

# Check if help is requested
if [ "$1" = "--help" ] && [ -z "$2" ]; then
    show_help
    exit 0
fi

# Set data directory environment variable
export BUNKR_DOWNLOAD_DIR="/data/downloads"
export BUNKR_LOG_DIR="/data/logs"

# Ensure directories exist
ensure_dirs

echo "Running BunkrDownloader CLI"
echo "Downloads will be saved to $BUNKR_DOWNLOAD_DIR"
exec bunkrd "$@"