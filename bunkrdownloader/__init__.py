"""
BunkrDownloader - A tool to download files from Bunkr and Cyberdrop.
"""
__version__ = "1.0.0"

# Add dotenv loading
try:
    from dotenv import load_dotenv
    import os
    
    # Try to load from .env file if it exists
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    # python-dotenv is not installed, silently continue
    pass