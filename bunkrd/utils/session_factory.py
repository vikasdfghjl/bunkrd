"""
Session factory for the BunkrDownloader application.
Provides a centralized way to create and manage HTTP sessions.
"""

import logging
import requests
from ..config import USE_PROXY, DEFAULT_PROXY
from .request_utils import create_session_with_random_ua, add_proxy_to_session, get_random_user_agent

# Setup logging
logger = logging.getLogger(__name__)

class SessionFactory:
    """
    Factory class for creating and managing HTTP sessions.
    
    This class centralizes session creation logic to ensure consistent
    behavior across different components of the application.
    """
    
    @staticmethod
    def create_session(proxy_url=None):
        """
        Create a new requests session with appropriate headers and proxy settings.
        
        Args:
            proxy_url (str, optional): A proxy URL to use. If None and USE_PROXY is True,
                DEFAULT_PROXY will be used.
                
        Returns:
            requests.Session: A new session with random user agent and proxy if configured
        """
        # Determine effective proxy URL
        effective_proxy_url = proxy_url if proxy_url is not None else (DEFAULT_PROXY if USE_PROXY else None)
        
        # Create session with random user agent
        session = create_session_with_random_ua()
        
        # Add proxy if configured
        if effective_proxy_url:
            logger.info(f"Using proxy: {effective_proxy_url}")
            session = add_proxy_to_session(session, effective_proxy_url)
            
        return session
    
    @staticmethod
    def refresh_session(session):
        """
        Refresh an existing session with a new user agent.
        
        Args:
            session (requests.Session): The session to refresh
            
        Returns:
            requests.Session: The refreshed session
        """
        session.headers['User-Agent'] = get_random_user_agent()
        logger.debug(f"Refreshed user agent: {session.headers['User-Agent'][:30]}...")
        return session