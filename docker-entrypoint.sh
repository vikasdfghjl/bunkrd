#!/bin/bash
set -e

# Function to display help
show_help() {
    echo "BunkrDownloader Docker Container"
    echo ""
    echo "Usage:"
    echo "  docker run [docker-options] bunkrdownloader [MODE] [options]"
    echo ""
    echo "Modes:"
    echo "  web          Run in web UI mode (default port: 5000)"
    echo "  cli          Run in CLI mode"
    echo "  --help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Run web UI on port 8080"
    echo "  docker run -p 8080:5000 -v /path/to/downloads:/data/downloads bunkrdownloader web"
    echo ""
    echo "  # Run CLI with a URL"
    echo "  docker run -v /path/to/downloads:/data/downloads bunkrdownloader cli -u https://bunkr.sk/a/example"
    echo ""
    echo "  # Show CLI help"
    echo "  docker run bunkrdownloader cli --help"
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
if [ "$1" = "--help" ] || [ -z "$1" ]; then
    show_help
    exit 0
fi

# Set data directory environment variable
export BUNKR_DOWNLOAD_DIR="/data/downloads"
export BUNKR_LOG_DIR="/data/logs"

# Ensure directories exist
ensure_dirs

# Route based on mode
case "$1" in
    web)
        shift  # Remove 'web' from arguments
        # Check port (parse from args if provided)
        PORT=5000
        HOST="0.0.0.0"
        
        echo "Starting BunkrDownloader Web UI on $HOST:$PORT"
        echo "Downloads will be saved to $BUNKR_DOWNLOAD_DIR"
        
        # Create needed directories for web UI
        mkdir -p /app/bunkrd/web/static/css
        mkdir -p /app/bunkrd/web/static/js
        mkdir -p /app/bunkrd/web/templates
        
        # Check if Flask is installed
        if ! pip list | grep -q Flask; then
            echo "Flask is not installed. Installing..."
            pip install flask
        fi
        
        exec python -m bunkrd.web.app "$@"
        ;;
        
    cli)
        shift  # Remove 'cli' from arguments
        echo "Running BunkrDownloader CLI"
        echo "Downloads will be saved to $BUNKR_DOWNLOAD_DIR"
        exec bunkrd "$@"
        ;;
        
    *)
        echo "Unknown mode: $1"
        echo ""
        show_help
        exit 1
        ;;
esac