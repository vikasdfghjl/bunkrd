"""
Request utility functions for the BunkrDownloader application.

This module provides utilities for managing HTTP requests including:
- Rate limiting
- Random delays
- Proxy support
- User-agent rotation
- Robots.txt compliance
- Memory management
- Thread scaling based on system resources
"""
import time
import random
import logging
import requests
import gc
import psutil
import sys
import os
import multiprocessing
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from ..config import REQUEST_HEADERS, DEFAULT_USER_AGENTS, MIN_REQUEST_DELAY, MAX_REQUEST_DELAY

logger = logging.getLogger(__name__)

# Store robots.txt parsers to avoid fetching them multiple times
_ROBOTS_PARSERS = {}

# Memory management thresholds (as percentage)
MEMORY_WARNING_THRESHOLD = 80
MEMORY_CRITICAL_THRESHOLD = 90

# CPU usage threshold (as percentage)
CPU_HIGH_THRESHOLD = 85
CPU_CRITICAL_THRESHOLD = 95

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

def measure_connection_speed(session, url, sample_size=16384, timeout=5):
    """
    Measure the current connection speed to a given URL.
    
    Args:
        session (requests.Session): Session to use for the request
        url (str): URL to test connection speed with
        sample_size (int): Size of the sample to download in bytes
        timeout (int): Timeout for the request in seconds
        
    Returns:
        float: Download speed in bytes per second, or None if measurement failed
    """
    try:
        # Use a HEAD request first to verify the URL is valid
        head_resp = session.head(url, timeout=timeout)
        if head_resp.status_code != 200:
            return None
        
        # Use Range header to request only a small sample
        headers = {'Range': f'bytes=0-{sample_size-1}'}
        
        # Measure download time for the sample
        start_time = time.time()
        response = session.get(url, headers=headers, timeout=timeout, stream=True)
        
        # Download the sample
        downloaded = 0
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                downloaded += len(chunk)
                
        # Calculate the download time and speed
        download_time = time.time() - start_time
        if download_time > 0 and downloaded > 0:
            speed = downloaded / download_time
            logger.debug(f"Measured connection speed: {speed/1024/1024:.2f} MB/s")
            return speed
        return None
    except Exception as e:
        logger.debug(f"Failed to measure connection speed: {str(e)}")
        return None

def get_memory_usage():
    """
    Get the current memory usage of the process.
    
    Returns:
        dict: Memory usage information including:
            - percent: Memory usage as percentage
            - used_mb: Used memory in MB
            - total_mb: Total system memory in MB
            - py_used_mb: Python process memory usage in MB
    """
    try:
        # Get system memory information
        system_memory = psutil.virtual_memory()
        
        # Get this process memory information
        process = psutil.Process()
        process_memory = process.memory_info().rss  # Resident Set Size in bytes
        
        return {
            'percent': system_memory.percent,
            'used_mb': system_memory.used / (1024 * 1024),
            'total_mb': system_memory.total / (1024 * 1024),
            'py_used_mb': process_memory / (1024 * 1024)
        }
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        return None

def check_memory_usage(force_collect=False):
    """
    Check memory usage and perform garbage collection if needed.
    
    Args:
        force_collect (bool): Force garbage collection regardless of memory usage
        
    Returns:
        bool: True if garbage collection was performed, False otherwise
    """
    memory = get_memory_usage()
    if memory is None:
        return False
        
    if force_collect or memory['percent'] > MEMORY_WARNING_THRESHOLD:
        # Log memory state before collection
        logger.debug(f"Memory usage before GC: {memory['percent']:.1f}% "
                     f"(Process: {memory['py_used_mb']:.1f}MB)")
        
        # Perform garbage collection
        collected = gc.collect()
        
        # Get memory usage after collection
        post_memory = get_memory_usage()
        if post_memory:
            memory_freed = memory['py_used_mb'] - post_memory['py_used_mb']
            logger.debug(f"GC collected {collected} objects, freed {memory_freed:.1f}MB, "
                         f"usage now {post_memory['percent']:.1f}% "
                         f"(Process: {post_memory['py_used_mb']:.1f}MB)")
            
            # If memory is still critical, log a warning
            if post_memory['percent'] > MEMORY_CRITICAL_THRESHOLD:
                logger.warning(f"Memory usage critically high: {post_memory['percent']:.1f}%")
                
        return True
        
    return False

def clear_memory_for_large_download(min_memory_mb=100):
    """
    Clear memory before downloading a large file.
    
    This function ensures there's enough memory available for a large download
    by forcing garbage collection and clearing caches.
    
    Args:
        min_memory_mb (int): Minimum memory in MB to try to free up
        
    Returns:
        int: Estimated freed memory in MB
    """
    # Get initial memory state
    initial_memory = get_memory_usage()
    if initial_memory is None:
        return 0
        
    logger.debug(f"Preparing memory for large download, current usage: "
                 f"{initial_memory['percent']:.1f}% (Process: {initial_memory['py_used_mb']:.1f}MB)")
    
    # Force garbage collection
    gc.collect(2)  # Full collection with all generations
    
    # Clear some module caches if they exist
    cleared_caches = 0
    
    # Clear robots parser cache if it's large
    global _ROBOTS_PARSERS
    if len(_ROBOTS_PARSERS) > 10:
        old_size = len(_ROBOTS_PARSERS)
        # Keep only the 5 most recently used parsers
        _ROBOTS_PARSERS = dict(list(_ROBOTS_PARSERS.items())[-5:])
        cleared_caches += old_size - len(_ROBOTS_PARSERS)
    
    # Clear requests session cache if possible
    if hasattr(requests, 'sessions') and hasattr(requests.sessions, '__cache__'):
        requests.sessions.__cache__.clear()
        cleared_caches += 1
    
    # Clear urllib cache if necessary
    if 'urllib.parse' in sys.modules:
        urlparse_cache = getattr(sys.modules['urllib.parse'], '_parse_cache', None)
        if urlparse_cache and len(urlparse_cache) > 100:
            urlparse_cache.clear()
            cleared_caches += 1
    
    # Get final memory state
    final_memory = get_memory_usage()
    if final_memory is None:
        return 0
        
    memory_freed = initial_memory['py_used_mb'] - final_memory['py_used_mb']
    logger.debug(f"Memory cleanup freed {memory_freed:.1f}MB, cleared {cleared_caches} caches, "
                 f"usage now {final_memory['percent']:.1f}% "
                 f"(Process: {final_memory['py_used_mb']:.1f}MB)")
    
    return memory_freed

def get_cpu_usage():
    """
    Get the current CPU usage of the system.
    
    Returns:
        dict: CPU usage information including:
            - system_percent: Overall system CPU usage percentage
            - process_percent: This process CPU usage percentage
            - cores: Number of CPU cores available
            - load_per_core: System load per core
    """
    try:
        # Get system CPU information
        system_percent = psutil.cpu_percent(interval=0.1)
        
        # Get this process CPU information
        process = psutil.Process()
        process_percent = process.cpu_percent(interval=0.1)
        
        # Get logical CPU cores
        cpu_count = psutil.cpu_count(logical=True)
        if not cpu_count:
            # Fallback to os.cpu_count()
            cpu_count = os.cpu_count() or 1
        
        # Get CPU load average (1, 5, 15 min) on *nix systems
        if hasattr(os, 'getloadavg'):
            try:
                load_avg = os.getloadavg()[0]  # 1 minute average
                load_per_core = load_avg / cpu_count
            except (OSError, AttributeError):
                load_per_core = system_percent / 100.0
        else:
            # On Windows, use current CPU percentage as an approximation
            load_per_core = system_percent / 100.0
        
        return {
            'system_percent': system_percent,
            'process_percent': process_percent,
            'cores': cpu_count,
            'load_per_core': load_per_core
        }
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return None

def get_optimal_thread_count(max_threads=None, min_threads=1, target_load_factor=0.75):
    """
    Determine the optimal number of threads for concurrent downloads based on 
    current system resources.
    
    Args:
        max_threads (int, optional): Maximum number of threads allowed
        min_threads (int, optional): Minimum number of threads to use
        target_load_factor (float, optional): Target CPU load factor per core (0-1)
        
    Returns:
        int: Recommended number of threads
    """
    # Get current CPU information
    cpu_info = get_cpu_usage()
    if not cpu_info:
        # Fallback to conservative default if we can't get CPU info
        return min_threads
    
    # Get memory information
    memory_info = get_memory_usage()
    
    # Get the number of CPU cores
    cpu_cores = cpu_info.get('cores', multiprocessing.cpu_count())
    
    # Start with CPU cores as the base number
    base_threads = max(1, int(cpu_cores * target_load_factor))
    
    # If CPU is already heavily loaded, reduce threads
    if cpu_info.get('system_percent', 0) > CPU_HIGH_THRESHOLD:
        reduction_factor = 0.6  # Reduce by 40%
        logger.debug(f"CPU usage high ({cpu_info['system_percent']:.1f}%), reducing thread count")
    elif cpu_info.get('system_percent', 0) > CPU_CRITICAL_THRESHOLD:
        reduction_factor = 0.4  # Reduce by 60%
        logger.warning(f"CPU usage critical ({cpu_info['system_percent']:.1f}%), severely limiting threads")
    else:
        reduction_factor = 1.0  # No reduction
    
    base_threads = max(1, int(base_threads * reduction_factor))
    
    # If memory is constrained, further reduce thread count
    if memory_info and memory_info.get('percent', 0) > MEMORY_WARNING_THRESHOLD:
        memory_factor = 1 - ((memory_info['percent'] - MEMORY_WARNING_THRESHOLD) / 
                            (100 - MEMORY_WARNING_THRESHOLD))
        base_threads = max(1, int(base_threads * memory_factor))
        logger.debug(f"Memory usage high ({memory_info['percent']:.1f}%), "
                    f"applying memory factor: {memory_factor:.2f}")
    
    # Apply limits
    if max_threads is not None:
        thread_count = min(max_threads, max(min_threads, base_threads))
    else:
        thread_count = max(min_threads, base_threads)
    
    logger.debug(f"Optimal thread count determined: {thread_count} "
                f"(CPU: {cpu_cores} cores, Load: {cpu_info.get('system_percent', 0):.1f}%, "
                f"Memory: {memory_info.get('percent', 0) if memory_info else 'Unknown'}%)")
    
    return thread_count

def adjust_concurrent_downloads(current_threads, max_threads=None, connection_speed=None,
                                consecutive_errors=0, download_success_rate=1.0):
    """
    Dynamically adjust the number of concurrent downloads based on system load,
    network performance, and error rates.
    
    Args:
        current_threads (int): Current number of threads in use
        max_threads (int, optional): Maximum threads allowed
        connection_speed (float, optional): Measured connection speed in bytes/second
        consecutive_errors (int, optional): Number of consecutive download errors
        download_success_rate (float, optional): Ratio of successful to total downloads (0-1)
        
    Returns:
        int: Adjusted number of threads
    """
    # Start with the optimal thread count based on system resources
    optimal_threads = get_optimal_thread_count(max_threads=max_threads)
    
    # Factor in connection speed (if provided)
    if connection_speed is not None:
        # Define connection speed thresholds in bytes/sec
        SLOW_NET = 256 * 1024      # 256 KB/s
        MEDIUM_NET = 1024 * 1024   # 1 MB/s
        FAST_NET = 5 * 1024 * 1024 # 5 MB/s
        
        if connection_speed < SLOW_NET:
            # For very slow connections, reduce concurrency
            net_factor = 0.5  # Reduce by 50%
            logger.debug(f"Slow connection ({connection_speed/1024:.1f} KB/s), reducing thread count")
        elif connection_speed < MEDIUM_NET:
            # For medium connections, slight reduction
            net_factor = 0.8  # Reduce by 20%
            logger.debug(f"Medium connection ({connection_speed/1024/1024:.2f} MB/s), slightly reducing thread count")
        elif connection_speed > FAST_NET:
            # For fast connections, allow slight increase
            net_factor = 1.2  # Increase by 20%
            logger.debug(f"Fast connection ({connection_speed/1024/1024:.2f} MB/s), can increase thread count")
        else:
            # For normal connections, no change
            net_factor = 1.0
        
        optimal_threads = max(1, int(optimal_threads * net_factor))
    
    # Factor in error rates
    if consecutive_errors >= 3:
        # Significant reduction if we're seeing consecutive errors
        error_factor = max(0.3, 1.0 - (consecutive_errors * 0.1))  # Reduce by 10% per error, max 70% reduction
        optimal_threads = max(1, int(optimal_threads * error_factor))
        logger.debug(f"Consecutive errors ({consecutive_errors}), applying error factor: {error_factor:.2f}")
    
    # Consider overall success rate for downloads
    if download_success_rate < 0.8:
        # If less than 80% of downloads are succeeding, reduce concurrency
        success_factor = max(0.5, download_success_rate)
        optimal_threads = max(1, int(optimal_threads * success_factor))
        logger.debug(f"Low success rate ({download_success_rate:.2f}), applying success factor: {success_factor:.2f}")
    
    # Don't change too drastically from current setting
    if optimal_threads > current_threads:
        # When increasing, do so gradually (add at most 2 threads)
        new_threads = min(optimal_threads, current_threads + 2)
    elif optimal_threads < current_threads:
        # When decreasing, do so more aggressively if needed
        if consecutive_errors >= 3 or download_success_rate < 0.5:
            # More aggressive reduction for error scenarios
            new_threads = optimal_threads
        else:
            # Gradual reduction otherwise (reduce by at most 1 thread)
            new_threads = max(optimal_threads, current_threads - 1)
    else:
        # No change needed
        new_threads = current_threads
    
    # Apply final bounds
    if max_threads is not None:
        new_threads = min(max_threads, new_threads)
    
    # If we're changing the thread count, log the reason
    if new_threads != current_threads:
        logger.info(f"Adjusting concurrent downloads from {current_threads} to {new_threads} threads " +
                   f"(Optimal: {optimal_threads}, " +
                   f"CPU: {get_cpu_usage().get('system_percent', 0):.1f}% " if get_cpu_usage() else "CPU: Unknown " +
                   f"Memory: {get_memory_usage().get('percent', 0):.1f}%)" if get_memory_usage() else "Memory: Unknown)")
    
    return new_threads