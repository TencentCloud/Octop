"""REST API Client Module

Provides synchronous and asynchronous HTTP client for API testing.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Callable
from urllib.parse import urljoin

import httpx
import requests
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class RestConfig:
    """Configuration for REST client."""
    base_url: str = ""
    timeout: int = 30
    retries: int = 3
    headers: Dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    follow_redirects: bool = True


class RestClient:
    """REST API Client with sync and async support."""
    
    def __init__(self, config: Optional[RestConfig] = None):
        self.config = config or RestConfig()
        self.session = requests.Session()
        self.interceptors: List[Any] = []
        
        # Configure session
        self.session.headers.update(self.config.headers)
        self.session.verify = self.config.verify_ssl
        
    def add_interceptor(self, interceptor):
        """Add request/response interceptor."""
        self.interceptors.append(interceptor)
        
    def set_auth(self, token: Optional[str] = None, username: Optional[str] = None, 
                 password: Optional[str] = None):
        """Set authentication."""
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            self.session.auth = (username, password)
    
    def _url(self, path: str) -> str:
        """Build full URL."""
        if self.config.base_url:
            return urljoin(self.config.base_url, path)
        return path
    
    def _apply_interceptors(self, request_or_response, is_request=True):
        """Apply registered interceptors."""
        for interceptor in self.interceptors:
            try:
                if is_request and hasattr(interceptor, 'before_request'):
                    interceptor.before_request(request_or_response)
                elif not is_request and hasattr(interceptor, 'after_response'):
                    interceptor.after_response(request_or_response)
            except Exception:
                pass
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry."""
        url = self._url(path)
        
        # Apply request interceptors
        request = requests.Request(method, url, **kwargs)
        self._apply_interceptors(request, is_request=True)
        
        response = self.session.request(method, url, timeout=self.config.timeout, **kwargs)
        
        # Apply response interceptors
        self._apply_interceptors(response, is_request=False)
        
        return response
    
    def get(self, path: str, **kwargs) -> requests.Response:
        """Make GET request."""
        return self.request("GET", path, **kwargs)
    
    def post(self, path: str, **kwargs) -> requests.Response:
        """Make POST request."""
        return self.request("POST", path, **kwargs)
    
    def put(self, path: str, **kwargs) -> requests.Response:
        """Make PUT request."""
        return self.request("PUT", path, **kwargs)
    
    def patch(self, path: str, **kwargs) -> requests.Response:
        """Make PATCH request."""
        return self.request("PATCH", path, **kwargs)
    
    def delete(self, path: str, **kwargs) -> requests.Response:
        """Make DELETE request."""
        return self.request("DELETE", path, **kwargs)
    
    def async_session(self):
        """Create async HTTP client session."""
        return AsyncRestClient(self.config)
    
    def close(self):
        """Close the session."""
        self.session.close()


class AsyncRestClient:
    """Async REST API Client."""
    
    def __init__(self, config: RestConfig):
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=self.config.headers,
            verify=self.config.verify_ssl,
            follow_redirects=self.config.follow_redirects
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make async HTTP request."""
        response = await self.client.request(method, path, **kwargs)
        return response
    
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make async GET request."""
        return await self.request("GET", path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make async POST request."""
        return await self.request("POST", path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """Make async PUT request."""
        return await self.request("PUT", path, **kwargs)
    
    async def patch(self, path: str, **kwargs) -> httpx.Response:
        """Make async PATCH request."""
        return await self.request("PATCH", path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """Make async DELETE request."""
        return await self.request("DELETE", path, **kwargs)
