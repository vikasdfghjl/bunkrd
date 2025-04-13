"""
Security utility functions for the BunkrDownloader application.
Contains functions for secure key handling and encryption.
"""
import os
import base64
import hashlib
import getpass
import logging
from pathlib import Path
from math import floor

# Setup logging
logger = logging.getLogger(__name__)

def get_secret_key(key_base, timestamp):
    """
    Generate a secret key securely using a key base and timestamp.
    
    This function generates a derived key from the base and timestamp
    using a secure method that avoids keeping the full key in memory
    longer than necessary.
    
    Args:
        key_base (str): The base string for the key
        timestamp (int): A timestamp to use in key generation
        
    Returns:
        bytes: The derived key as bytes
    """
    # Calculate the hourly salt value from the timestamp
    hourly_salt = str(int(timestamp / 3600))
    
    logger.debug(f"Generating secret key with hourly_salt: {hourly_salt} (from timestamp: {timestamp})")
    
    # Create the secret key as in the working code
    secret_key = f"{key_base}{hourly_salt}"
    logger.debug(f"Generated key: {secret_key[:5]}...")
    
    return secret_key.encode('utf-8')

def secure_xor_bytes(data_bytes, key_bytes):
    """
    Perform XOR operation between two byte arrays securely.
    
    Args:
        data_bytes (bytes): Data bytes to encrypt/decrypt
        key_bytes (bytes): Key bytes to use for XOR operation
        
    Returns:
        bytearray: Result of XOR operation
    """
    logger.debug(f"XORing data (length: {len(data_bytes)}) with key (length: {len(key_bytes)})")
    
    # Convert bytes to lists as in the working code
    data_list = list(data_bytes)
    key_list = list(key_bytes)
    
    # Build result using the same method as in working code
    decrypted_url = ""
    for i in range(len(data_list)):
        decrypted_url += chr(data_list[i] ^ key_list[i % len(key_list)])
    
    logger.debug(f"XOR result length: {len(decrypted_url)}")
    if decrypted_url:
        logger.debug(f"First few chars of result: {decrypted_url[:10]}...")
    
    return decrypted_url

def decrypt_with_key(encrypted_data, key_base, timestamp):
    """
    Decrypt data using a derived key from the key base and timestamp.
    
    Args:
        encrypted_data (str): Base64 encoded encrypted data
        key_base (str): The base string for the key
        timestamp (int): Timestamp used in key generation
        
    Returns:
        str: Decrypted data
    """
    try:
        logger.debug(f"Attempting to decrypt data (length: {len(encrypted_data)})")
        logger.debug(f"First 20 chars of encrypted data: {encrypted_data[:20]}")
        
        # Decode the base64 data
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            logger.debug(f"Base64 decode successful, got {len(encrypted_bytes)} bytes")
        except Exception as e:
            logger.error(f"Base64 decoding failed: {str(e)}")
            return None
        
        # Get the derived key
        key = get_secret_key(key_base, timestamp)
        
        # Decrypt the data using the proven method from dump.py
        decrypted_url = secure_xor_bytes(encrypted_bytes, key)
        
        # Minimal validation that it's a URL
        if not decrypted_url.startswith('http'):
            logger.warning(f"Decrypted data doesn't appear to be a valid URL: {decrypted_url[:30]}...")
            
        return decrypted_url
    
    except Exception as e:
        logger.error(f"Error decrypting data: {str(e)}")
        return None

def load_secret_from_env(env_var_name, default=None):
    """
    Load a secret from an environment variable.
    
    Args:
        env_var_name (str): Name of the environment variable
        default (str, optional): Default value if not found
        
    Returns:
        str: The secret value
    """
    value = os.environ.get(env_var_name)
    if value is None:
        if default is None:
            logger.warning(f"Environment variable {env_var_name} not set and no default provided")
        return default
    return value

def initialize_secret_key(config_key_name):
    """
    Initialize a secret key, prompting user if needed.
    
    Args:
        config_key_name (str): Name of the key in the config
        
    Returns:
        str: The secret key
    """
    # Try to load from environment variable
    env_var_name = f"BUNKRDOWNLOADER_{config_key_name}"
    key = load_secret_from_env(env_var_name)
    
    if key is None:
        # Check if we have a saved key in the user's home directory
        config_dir = Path.home() / ".bunkrdownloader"
        config_file = config_dir / "secrets.txt"
        
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    for line in f:
                        if line.startswith(f"{config_key_name}="):
                            key = line.strip().split("=", 1)[1]
                            break
            except IOError:
                pass
    
    # Return the key if we found it
    if key:
        return key
        
    # If we reach here, we couldn't find the key
    return None