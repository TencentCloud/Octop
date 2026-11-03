"""Assertions Module

Provides convenient assertion methods for API testing.
"""

import json
from typing import Any, Dict, List, Optional, Union

import requests
import httpx
from jsonschema import validate, ValidationError


class Assertions:
    """Assertion helpers for API testing."""
    
    @staticmethod
    def assert_status_code(response: Union[requests.Response, httpx.Response], 
                          expected: Union[int, List[int]]) -> None:
        """Assert response status code."""
        if isinstance(expected, int):
            expected = [expected]
        assert response.status_code in expected, \
            f"Expected status code {expected}, got {response.status_code}"
    
    @staticmethod
    def assert_ok(response: Union[requests.Response, httpx.Response]) -> None:
        """Assert 2xx status code."""
        assert 200 <= response.status_code < 300, \
            f"Expected 2xx, got {response.status_code}"
    
    @staticmethod
    def assert_json_content_type(response: Union[requests.Response, httpx.Response]) -> None:
        """Assert JSON content type."""
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, \
            f"Expected JSON content type, got {content_type}"
    
    @staticmethod
    def assert_json_contains(response: Union[requests.Response, httpx.Response], 
                            key: str) -> None:
        """Assert JSON contains key."""
        data = response.json()
        assert key in data, f"Expected JSON to contain key '{key}'"
    
    @staticmethod
    def assert_json_path(response: Union[requests.Response, httpx.Response],
                        path: str, expected_value: Any) -> None:
        """Assert JSON path has expected value.
        
        Simple path format: key1.key2[0].key3
        """
        data = response.json()
        
        # Simple path navigation
        current = data
        keys = path.replace("[", ".").replace("]", "").split(".")
        
        for key in keys:
            if key.isdigit():
                current = current[int(key)]
            else:
                current = current[key]
        
        assert current == expected_value, \
            f"Expected {path}={expected_value}, got {current}"
    
    @staticmethod
    def assert_json_schema(response: Union[requests.Response, httpx.Response],
                          schema: Dict[str, Any]) -> None:
        """Assert response matches JSON schema."""
        data = response.json()
        try:
            validate(instance=data, schema=schema)
        except ValidationError as e:
            raise AssertionError(f"Schema validation failed: {e.message}")
    
    @staticmethod
    def assert_header_contains(response: Union[requests.Response, httpx.Response],
                              header: str, expected: str) -> None:
        """Assert header contains expected value."""
        header_value = response.headers.get(header, "")
        assert expected in header_value, \
            f"Expected header '{header}' to contain '{expected}', got '{header_value}'"
    
    @staticmethod
    def assert_header_equals(response: Union[requests.Response, httpx.Response],
                            header: str, expected: str) -> None:
        """Assert header equals expected value."""
        header_value = response.headers.get(header)
        assert header_value == expected, \
            f"Expected header '{header}'='{expected}', got '{header_value}'"
    
    @staticmethod
    def assert_response_time(response: Union[requests.Response, httpx.Response],
                            max_time: float) -> None:
        """Assert response time is within limit.
        
        Note: For requests, this requires timing wrapper.
        For httpx, response.elapsed is available.
        """
        if hasattr(response, 'elapsed'):
            elapsed = response.elapsed.total_seconds()
            assert elapsed <= max_time, \
                f"Response time {elapsed}s exceeded max {max_time}s"
    
    @staticmethod
    def assert_json_length(response: Union[requests.Response, httpx.Response],
                          path: Optional[str], expected: int) -> None:
        """Assert JSON array length."""
        data = response.json()
        
        if path:
            keys = path.replace("[", ".").replace("]", "").split(".")
            for key in keys:
                if key.isdigit():
                    data = data[int(key)]
                else:
                    data = data[key]
        
        actual = len(data) if hasattr(data, '__len__') else 0
        assert actual == expected, \
            f"Expected length {expected}, got {actual}"
    
    @staticmethod
    def assert_not_empty(response: Union[requests.Response, httpx.Response],
                        path: Optional[str] = None) -> None:
        """Assert response or path is not empty."""
        data = response.json()
        
        if path:
            keys = path.replace("[", ".").replace("]", "").split(".")
            for key in keys:
                if key.isdigit():
                    data = data[int(key)]
                else:
                    data = data[key]
        
        if isinstance(data, (list, dict, str)):
            assert len(data) > 0, "Expected non-empty data"
        else:
            assert data is not None, "Expected non-null data"
    
    @staticmethod
    def assert_contains(response: Union[requests.Response, httpx.Response],
                       expected: Union[str, Dict, List]) -> None:
        """Assert response contains expected data."""
        data = response.json()
        
        if isinstance(expected, dict):
            for key, value in expected.items():
                assert key in data, f"Expected key '{key}' not found"
                assert data[key] == value, \
                    f"Expected {key}={value}, got {data[key]}"
        elif isinstance(expected, list):
            for item in expected:
                assert item in data, f"Expected item '{item}' not found"
        else:
            assert expected in str(data), f"Expected '{expected}' not found in response"
