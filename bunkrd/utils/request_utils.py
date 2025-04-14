"""
Request utility functions for the BunkrDownloader application.

This module provides utilities for managing HTTP requests including:
- Rate limiting
- Random delays
- Proxy support
- User-agent rotation
- Robots.txt compliance
"""
import time
import random
import requests
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from ..config import REQUEST_HEADERS, DEFAULT_USER_AGENTS, MIN_REQUEST_DELAY, MAX_REQUEST_DELAY

# Store robots.txt parsers to avoid fetching them multiple times
_ROBOTS_PARSERS = {}

def get_random_delay():
    """
    Get a random delay value between MIN_REQUEST_DELAY and MAX_REQUEST_DELAY.
    
    Returns:
        float: A random delay in seconds
    """
    return random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)

def sleep_with_random_delay(min_delay=None, max_delay=None):
    """
    Sleep for a random amount of time to simulate human behavior.
    
    Args:
        min_delay (float, optional): Minimum delay in seconds. If None, uses MIN_REQUEST_DELAY from config.
        max_delay (float, optional): Maximum delay in seconds. If None, uses MAX_REQUEST_DELAY from config.
        
    Returns:
        float: The actual delay used in seconds
    """
    min_delay = MIN_REQUEST_DELAY if min_delay is None else min_delay
    max_delay = MAX_REQUEST_DELAY if max_delay is None else max_delay
    
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)
    return delay

def get_random_user_agent():
    """
    Get a random user agent from the configured list.
    
    Returns:
        str: A random user agent string
    """
    return random.choice(DEFAULT_USER_AGENTS)

def create_session_with_random_ua():
    """
    Create a session with a randomly selected user agent.
    
    Returns:
        requests.Session: A session with random user agent
    """
    session = requests.Session()
    headers = REQUEST_HEADERS.copy()
    headers['User-Agent'] = get_random_user_agent()
    session.headers.update(headers)
    return session

def add_proxy_to_session(session, proxy_url=None):
    """
    Add proxy settings to a session.
    
    Args:
        session (requests.Session): The session to configure
        proxy_url (str, optional): Proxy URL to use (e.g., 'socks5://127.0.0.1:9050')
            If None, no proxy will be added
    
    Returns:
        requests.Session: The configured session
    """
    if proxy_url:
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
    return session

def can_fetch(url, user_agent="*"):
    """
    Check if robots.txt allows access to the given URL.
    
    Args:
        url (str): URL to check
        user_agent (str, optional): User-agent to check permissions for
            
    Returns:
        bool: True if fetching is allowed, False otherwise
    """
    try:
        parsed_url = urlparse(url)
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        
        # Check if we've already parsed this robots.txt
        if robots_url not in _ROBOTS_PARSERS:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception as e:
                print(f"[*] Warning: Could not fetch robots.txt at {robots_url}: {e}")
                # If we can't fetch robots.txt, assume access is allowed
                return True
            
            _ROBOTS_PARSERS[robots_url] = parser
            
        return _ROBOTS_PARSERS[robots_url].can_fetch(user_agent, url)
    except Exception as e:
        print(f"[*] Error checking robots.txt for {url}: {e}")
        # In case of error, assume access is allowed
        return True

def make_request_with_rate_limit(session, method, url, check_robots=True, **kwargs):
    """
    Make an HTTP request with rate limiting and other protections.
    
    Args:
        session (requests.Session): Session to use
        method (str): HTTP method (get, post, etc.)
        url (str): URL to request
        check_robots (bool, optional): Whether to check robots.txt before making the request
        **kwargs: Additional arguments to pass to the request method
        
    Returns:
        requests.Response: The response from the server
    """
    # Add random delay
    sleep_with_random_delay()
    
    # Update user agent for each request
    current_headers = session.headers.copy()
    current_headers['User-Agent'] = get_random_user_agent()
    
    # Check robots.txt
    if check_robots and not can_fetch(url, current_headers.get('User-Agent')):
        print(f"[*] Warning: robots.txt denies access to {url}")
        # Return a fake response with 403 status
        response = requests.Response()
        response.status_code = 403
        response.url = url
        response._content = b"Access denied by robots.txt"
        return response
    
    # Make the request with the updated user agent
    kwargs['headers'] = current_headers
    request_method = getattr(session, method.lower())
    return request_method(url, **kwargs)