"""
Factory for creating parser instances based on URL.
"""
from .bunkr_parser import BunkrParser
from .cyberdrop_parser import CyberdropParser

class ParserFactory:
    """
    Factory class for creating the appropriate parser based on URL.
    """
    
    @staticmethod
    def get_parser(url, session=None, proxy_url=None):
        """
        Get the appropriate parser for a given URL.
        
        Args:
            url (str): The URL to get a parser for
            session (requests.Session, optional): A session to use for the parser
            proxy_url (str, optional): A proxy URL to use for the parser
            
        Returns:
            Parser: An instance of a parser for the URL
        """
        if 'bunkr' in url:
            return BunkrParser(session, proxy_url)
        elif 'cyberdrop' in url:
            return CyberdropParser(session, proxy_url)
        else:
            # Default to BunkrParser for unknown URLs
            return BunkrParser(session, proxy_url)