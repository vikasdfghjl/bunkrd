"""
File utility functions for the BunkrDownloader application.
"""
import os
import re
from urllib.parse import urlparse
from ..config import DEFAULT_DOWNLOAD_PATH, ALREADY_DOWNLOADED_FILE, URL_LIST_FILE

def get_url_data(url):
    """
    Parse a URL and extract its components.
    
    Args:
        url (str): The URL to parse
        
    Returns:
        dict: Dictionary containing file_name, extension, and hostname
    """
    try:
        parsed_url = urlparse(url)
        return {
            'file_name': os.path.basename(parsed_url.path) or 'unnamed_file',
            'extension': os.path.splitext(parsed_url.path)[1].lower(),
            'hostname': parsed_url.hostname
        }
    except Exception as e:
        print(f"[-] Error parsing URL {url}: {str(e)}")
        # Return default values that won't cause errors downstream
        return {'file_name': 'unnamed_file', 'extension': '', 'hostname': ''}

def get_and_prepare_download_path(base_path, album_name):
    """
    Get and prepare the download path based on the album name.
    
    Args:
        base_path (str): The base path for downloads
        album_name (str): The name of the album
        
    Returns:
        str: The path where files will be downloaded
    """
    if album_name:
        download_path = os.path.join(base_path or DEFAULT_DOWNLOAD_PATH, album_name)
    else:
        if base_path is None:
            # If both base_path and album_name are None, use the default path
            # This ensures backward compatibility with existing tests
            download_path = "downloads"
        else:
            # If base_path is provided but album_name is None, use base_path
            download_path = base_path
    
    # Create the directory if it doesn't exist
    if not os.path.exists(download_path):
        os.makedirs(download_path, exist_ok=True)
    
    # Create the already_downloaded.txt file if it doesn't exist
    already_downloaded_path = os.path.join(download_path, "already_downloaded.txt")
    if not os.path.exists(already_downloaded_path):
        with open(already_downloaded_path, 'w', encoding='utf-8') as f:
            pass  # Create an empty file
    
    return download_path

def write_url_to_list(item_url, download_path):
    """
    Write a URL to the url_list.txt file.
    
    Args:
        item_url (str): URL to write
        download_path (str): Path to the download directory
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        list_path = os.path.join(download_path, URL_LIST_FILE)
        with open(list_path, 'a', encoding='utf-8') as f:
            f.write(f"{item_url}\n")
        return True
    except IOError as e:
        print(f"[-] Error writing to url_list.txt: {str(e)}")
        return False
    except Exception as e:
        print(f"[-] Unexpected error writing URL to list: {str(e)}")
        return False

def get_already_downloaded_url(download_path):
    """
    Get a list of already downloaded URLs.
    
    Args:
        download_path (str): Path to the download directory
        
    Returns:
        list: List of URLs that have already been downloaded
    """
    try:
        file_path = os.path.join(download_path, ALREADY_DOWNLOADED_FILE)
        if not os.path.isfile(file_path):
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().splitlines()
        except IOError as e:
            print(f"[-] Error reading already_downloaded.txt: {str(e)}")
            return []
    except Exception as e:
        print(f"[-] Unexpected error getting already downloaded URLs: {str(e)}")
        return []

def mark_as_downloaded(item_url, download_path):
    """
    Mark a URL as downloaded by writing it to already_downloaded.txt.
    
    Args:
        item_url (str): The URL to mark as downloaded
        download_path (str): Path to the download directory
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        file_path = os.path.join(download_path, ALREADY_DOWNLOADED_FILE)
        try:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"{item_url}\n")
            return True
        except IOError as e:
            print(f"[-] Error updating already_downloaded.txt: {str(e)}")
            return False
    except Exception as e:
        print(f"[-] Unexpected error marking URL as downloaded: {str(e)}")
        return False

def remove_illegal_chars(string):
    """
    Remove illegal characters from a string for use as a filename.
    
    Args:
        string (str): The string to sanitize
        
    Returns:
        str: Sanitized string
    """
    try:
        if not string:
            return "unnamed"
        return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", string).strip()
    except Exception as e:
        print(f"[-] Error removing illegal characters: {str(e)}")
        return "unnamed"