"""
Factory for creating downloader instances based on URL.
"""
from .bunkr_downloader import BunkrDownloader
from .cyberdrop_downloader import CyberdropDownloader

class DownloaderFactory:
    """
    Factory class for creating the appropriate downloader based on URL.
    
    This factory class implements the Factory Method design pattern, providing a way to
    create different downloader objects based on the URL without exposing the creation
    logic to the client. This design makes it easy to add support for new sites by
    simply creating a new downloader class and adding it to this factory.
    """
    
    @staticmethod
    def get_downloader(url, session=None, proxy_url=None):
        """
        Get the appropriate downloader for a given URL.
        
        This method analyzes the URL to determine which site-specific downloader
        should handle the file download. Each downloader implements specialized logic
        for extracting download links from their respective sites.
        
        Args:
            url (str): The URL to get a downloader for - determines which site's
                       downloader implementation to use
            session (requests.Session, optional): A session to use for the downloader,
                       allowing for cookie persistence and connection pooling
            proxy_url (str, optional): A proxy URL to use for the downloader,
                       enabling anonymous downloads via proxy servers
            
        Returns:
            BaseDownloader: An instance of a specific downloader that can handle the given URL
        """
        if 'bunkr' in url:
            # Use BunkrDownloader for URLs containing 'bunkr' (handles bunkr.sk, bunkr.la, etc.)
            return BunkrDownloader(session, proxy_url)
        elif 'cyberdrop' in url:
            # Use CyberdropDownloader for URLs containing 'cyberdrop' (handles cyberdrop.me, etc.)
            return CyberdropDownloader(session, proxy_url)
        else:
            # Default to BunkrDownloader as a fallback for unknown domains
            # This allows handling of similar sites or new domains not explicitly supported yet
            return BunkrDownloader(session, proxy_url)