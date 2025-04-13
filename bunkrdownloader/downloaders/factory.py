"""
Factory for creating downloader instances based on URL.
"""
from .bunkr_downloader import BunkrDownloader
from .cyberdrop_downloader import CyberdropDownloader

class DownloaderFactory:
    """
    Factory class for creating the appropriate downloader based on URL.
    """
    
    @staticmethod
    def get_downloader(url, session=None, proxy_url=None):
        """
        Get the appropriate downloader for a given URL.
        
        Args:
            url (str): The URL to get a downloader for
            session (requests.Session, optional): A session to use for the downloader
            proxy_url (str, optional): A proxy URL to use for the downloader
            
        Returns:
            BaseDownloader: An instance of a downloader for the URL
        """
        if 'bunkr' in url:
            return BunkrDownloader(session, proxy_url)
        elif 'cyberdrop' in url:
            return CyberdropDownloader(session, proxy_url)
        else:
            # Default to BunkrDownloader for unknown URLs
            return BunkrDownloader(session, proxy_url)