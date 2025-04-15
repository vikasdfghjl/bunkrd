"""
Factory for creating parser instances based on URL.
"""
from .bunkr_parser import BunkrParser
from .cyberdrop_parser import CyberdropParser

class ParserFactory:
    """
    Factory class for creating the appropriate parser based on URL.
    
    This implementation follows the Factory Method design pattern, allowing the application
    to create parser objects without specifying their concrete classes. It creates
    parsers dynamically based on the URL's domain.
    """
    
    @staticmethod
    def get_parser(url, session=None, proxy_url=None):
        """
        Get the appropriate parser for a given URL.
        
        This method acts as the factory method that determines which parser to instantiate
        based on the URL's domain. It encapsulates object creation logic and provides
        a centralized place to handle new parser types in the future.
        
        Args:
            url (str): The URL to get a parser for - determines which parser type to create
            session (requests.Session, optional): A session to use for the parser
            proxy_url (str, optional): A proxy URL to use for the parser
            
        Returns:
            Parser: An instance of a parser appropriate for handling the given URL
        """
        if 'bunkr' in url:
            # Create BunkrParser for any URL containing 'bunkr'
            return BunkrParser(session, proxy_url)
        elif 'cyberdrop' in url:
            # Create CyberdropParser for any URL containing 'cyberdrop'
            return CyberdropParser(session, proxy_url)
        else:
            # Default to BunkrParser for unknown URLs as a fallback strategy
            return BunkrParser(session, proxy_url)
            
    @staticmethod
    def get_parser_with_options(url, session=None, proxy_url=None, use_incremental=True):
        """
        Get the appropriate parser for a given URL with additional options.
        
        This extended factory method allows specifying additional options like
        whether to use incremental parsing for large pages.
        
        Args:
            url (str): The URL to get a parser for - determines which parser type to create
            session (requests.Session, optional): A session to use for the parser
            proxy_url (str, optional): A proxy URL to use for the parser
            use_incremental (bool, optional): Whether to use incremental parsing
            
        Returns:
            tuple: (Parser instance, use_incremental flag)
        """
        parser = ParserFactory.get_parser(url, session, proxy_url)
        # For very large pages, ensure incremental parsing is used
        return parser, use_incremental