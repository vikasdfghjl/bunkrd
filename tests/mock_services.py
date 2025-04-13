"""
Mock services for testing the BunkrDownloader application without real network calls.

This module provides mock implementations of external services used by the application,
allowing tests to run without making real network requests.
"""
import json
import re
from urllib.parse import urlparse, parse_qs
from unittest.mock import Mock

class MockResponse:
    """Mock implementation of a requests.Response object."""
    
    def __init__(self, status_code=200, content=None, text="", url=None, headers=None):
        self.status_code = status_code
        self._content = content or b''
        self.text = text
        self.url = url or "https://mock-url.com"
        self.headers = headers or {}
        self.reason = "OK" if status_code == 200 else "Error"
        
    def json(self):
        """Return the content as parsed JSON."""
        return json.loads(self._content)
        
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass
        
    def iter_content(self, chunk_size=1024):
        """Simulate iterating through content chunks."""
        content_size = len(self._content)
        for i in range(0, content_size, chunk_size):
            yield self._content[i:i + chunk_size]


class MockBunkrService:
    """Mock service for Bunkr website."""
    
    def __init__(self):
        """Initialize the mock service with test data."""
        self.albums = {
            "test-album": {
                "name": "Test Album",
                "files": [
                    {"url": "https://bunkr.sk/f/test-file1.jpg", "slug": "test-file1"},
                    {"url": "https://bunkr.sk/f/test-file2.png", "slug": "test-file2"},
                ]
            }
        }
        
        self.files = {
            "test-file1": {
                "url": "mock-encrypted-url-1",
                "timestamp": 1649776000,
                "size": 1024 * 100  # 100KB
            },
            "test-file2": {
                "url": "mock-encrypted-url-2",
                "timestamp": 1649776000,
                "size": 1024 * 200  # 200KB
            }
        }
        
        # Mock file content (just random bytes)
        self.file_content = {
            "test-file1": b"x" * (1024 * 100),  # 100KB of data
            "test-file2": b"y" * (1024 * 200),  # 200KB of data
        }
    
    def get_album_page(self, album_id):
        """Get the HTML content of a mock album page."""
        if album_id not in self.albums:
            return MockResponse(status_code=404, text="Not found")
            
        album = self.albums[album_id]
        
        # Generate simple HTML for the album
        html = f"""
        <html>
        <head><title>Bunkr - {album['name']}</title></head>
        <body>
            <h1 class="block truncate">{album['name']}</h1>
            <div class="grid">
                {''.join([
                    f'<a href="{file["url"]}" class="shadow-md">{file["slug"]}</a>'
                    for file in album['files']
                ])}
            </div>
        </body>
        </html>
        """
        
        return MockResponse(
            status_code=200,
            text=html,
            url=f"https://bunkr.sk/a/{album_id}"
        )
    
    def get_api_response(self, slug):
        """Get a mock API response for a file slug."""
        if slug not in self.files:
            return MockResponse(status_code=404)
            
        file_data = self.files[slug]
        
        return MockResponse(
            status_code=200,
            content=json.dumps(file_data).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
    
    def get_file_content(self, file_id):
        """Get mock file content for a file ID."""
        if file_id not in self.file_content:
            return MockResponse(status_code=404)
            
        content = self.file_content[file_id]
        
        return MockResponse(
            status_code=200,
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content))
            }
        )


class MockRequestsSession:
    """Mock implementation of a requests.Session."""
    
    def __init__(self, mock_services=None):
        """Initialize with mock services."""
        self.headers = {
            "User-Agent": "mock-user-agent"
        }
        self.proxies = {}
        self.mock_services = mock_services or {
            "bunkr": MockBunkrService()
        }
    
    def get(self, url, **kwargs):
        """Mock GET request."""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path
        
        # Handle Bunkr requests
        if "bunkr" in domain:
            if "/a/" in path:  # Album page
                album_id = path.split("/a/")[1]
                return self.mock_services["bunkr"].get_album_page(album_id)
                
            elif "/f/" in path:  # File page
                file_id = path.split("/f/")[1]
                return self.mock_services["bunkr"].get_file_content(file_id)
        
        # Default response for unhandled URLs
        return MockResponse(
            status_code=404,
            text="Not found",
            url=url
        )
    
    def post(self, url, **kwargs):
        """Mock POST request."""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path
        
        # Handle Bunkr API requests
        if "bunkr" in domain and "/api/" in path:
            # Extract slug from request JSON
            json_data = kwargs.get('json', {})
            slug = json_data.get('slug')
            
            if slug:
                return self.mock_services["bunkr"].get_api_response(slug)
        
        # Default response
        return MockResponse(
            status_code=404,
            text="Not found",
            url=url
        )


def create_mock_session():
    """Create a mock requests session."""
    return MockRequestsSession()


def patch_requests_for_testing(monkeypatch):
    """
    Patch the requests library for testing.
    
    Args:
        monkeypatch: pytest's monkeypatch fixture
    """
    mock_session = create_mock_session()
    
    # Create a mock Session class that returns our mock session
    mock_session_class = Mock()
    mock_session_class.return_value = mock_session
    
    # Patch the requests.Session class
    monkeypatch.setattr("requests.Session", mock_session_class)
    
    # Return the mock session for further customization in tests
    return mock_session