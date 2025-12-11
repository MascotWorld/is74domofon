"""IS74 API Client for intercom integration."""

import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class IS74ApiError(Exception):
    """Base exception for IS74 API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)


class IS74ApiClient:
    """HTTP client for IS74 API with logging, error handling, and retry logic."""

    BASE_URL = "https://api.is74.ru"
    USER_AGENT = "4.12.0 com.intersvyaz.lk/1.30.1.2024040812"
    ACCEPT_HEADER = "application/json; version=v2"
    
    # Patterns for sensitive data masking
    SENSITIVE_PATTERNS = [
        (re.compile(r'"TOKEN"\s*:\s*"[^"]*"'), '"TOKEN": "***MASKED***"'),
        (re.compile(r'"PASSWORD"\s*:\s*"[^"]*"'), '"PASSWORD": "***MASKED***"'),
        (re.compile(r'"password"\s*:\s*"[^"]*"'), '"password": "***MASKED***"'),
        (re.compile(r'"phone"\s*:\s*"[^"]*"'), '"phone": "***MASKED***"'),
        (re.compile(r'"code"\s*:\s*"[^"]*"'), '"code": "***MASKED***"'),
        (re.compile(r'"access_token"\s*:\s*"[^"]*"'), '"access_token": "***MASKED***"'),
        (re.compile(r'"firebase_token"\s*:\s*"[^"]*"'), '"firebase_token": "***MASKED***"'),
        (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*'), 'Bearer ***MASKED***'),
        (re.compile(r'"authid"\s*:\s*"[^"]*"'), '"authid": "***MASKED***"'),
    ]

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        device_id: Optional[str] = None,
    ):
        """
        Initialize IS74 API client.

        Args:
            base_url: Base URL for IS74 API (defaults to https://td-crm.is74.ru)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
            device_id: Optional device ID to use (if None, generates new one)
        """
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Use provided device ID or generate new one (16 hex characters)
        if device_id:
            self._device_id = device_id
            logger.info(f"Using provided device_id: {device_id}")
        else:
            import uuid
            self._device_id = uuid.uuid4().hex[:16]
            logger.info(f"Generated new device_id: {self._device_id}")
        
        # Create httpx client with default headers
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": self.ACCEPT_HEADER,
                "X-Device-Id": self._device_id,
            },
            follow_redirects=True,
        )
        
        logger.info(f"IS74ApiClient initialized with base_url={self.base_url}")

    def _mask_sensitive_data(self, text: str) -> str:
        """
        Mask sensitive data in text for logging.

        Args:
            text: Text that may contain sensitive data

        Returns:
            Text with sensitive data masked
        """
        masked = text
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked

    def _log_request(self, method: str, url: str, **kwargs) -> None:
        """
        Log HTTP request with sensitive data masked.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request parameters
        """
        # Mask headers
        headers = kwargs.get("headers", {})
        masked_headers = {}
        for key, value in headers.items():
            if key.lower() in ["authorization", "x-api-key"]:
                masked_headers[key] = "***MASKED***"
            else:
                masked_headers[key] = value
        
        # Mask body
        body = kwargs.get("json") or kwargs.get("data")
        masked_body = None
        if body:
            # Convert to JSON string for masking
            import json
            try:
                body_str = json.dumps(body)
                masked_body = self._mask_sensitive_data(body_str)
            except (TypeError, ValueError):
                body_str = str(body)
                masked_body = self._mask_sensitive_data(body_str)
        
        logger.debug(
            f"API Request: {method} {url}",
            extra={
                "method": method,
                "url": url,
                "headers": masked_headers,
                "body": masked_body,
            }
        )

    def _log_response(self, response: httpx.Response) -> None:
        """
        Log HTTP response with sensitive data masked.

        Args:
            response: HTTP response object
        """
        try:
            response_text = response.text
            masked_text = self._mask_sensitive_data(response_text)
        except Exception:
            masked_text = "<unable to decode response>"
        
        logger.debug(
            f"API Response: {response.status_code}",
            extra={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": masked_text[:1000],  # Limit response body length
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response object

        Raises:
            IS74ApiError: If request fails after retries
        """
        url = endpoint if endpoint.startswith("http") else urljoin(self.base_url, endpoint)
        
        self._log_request(method, url, **kwargs)
        
        try:
            response = await self.client.request(method, url, **kwargs)
            self._log_response(response)
            
            # Raise exception for HTTP errors
            if response.status_code >= 400:
                error_data = None
                try:
                    error_data = response.json()
                except Exception:
                    error_data = {"detail": response.text}
                
                raise IS74ApiError(
                    f"API request failed: {response.status_code} {response.reason_phrase}",
                    status_code=response.status_code,
                    response_data=error_data,
                )
            
            return response
            
        except httpx.TimeoutException as e:
            logger.error(f"Request timeout: {method} {url}")
            raise IS74ApiError(f"Request timeout: {str(e)}") from e
        except httpx.NetworkError as e:
            logger.error(f"Network error: {method} {url}")
            raise IS74ApiError(f"Network error: {str(e)}") from e
        except IS74ApiError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during request: {method} {url}", exc_info=True)
            raise IS74ApiError(f"Unexpected error: {str(e)}") from e

    async def get(self, endpoint: str, params: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Make GET request to IS74 API.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            **kwargs: Additional arguments for request

        Returns:
            Response data as dictionary
        """
        if params:
            kwargs['params'] = params
        response = await self._request("GET", endpoint, **kwargs)
        return response.json()

    async def post(self, endpoint: str, params: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Make POST request to IS74 API.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            **kwargs: Additional arguments for request (json, data, content, headers, etc.)

        Returns:
            Response data as dictionary
        """
        # If 'data' is provided, ensure Content-Type is set for form encoding
        if 'data' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {}
        if 'data' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
            kwargs['headers']['Content-Type'] = 'application/x-www-form-urlencoded'
        
        if params:
            kwargs['params'] = params
        
        response = await self._request("POST", endpoint, **kwargs)
        return response.json()

    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make PUT request to IS74 API.

        Args:
            endpoint: API endpoint path
            **kwargs: Additional arguments for request

        Returns:
            Response data as dictionary
        """
        response = await self._request("PUT", endpoint, **kwargs)
        return response.json()

    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make DELETE request to IS74 API.

        Args:
            endpoint: API endpoint path
            **kwargs: Additional arguments for request

        Returns:
            Response data as dictionary
        """
        response = await self._request("DELETE", endpoint, **kwargs)
        return response.json()

    def set_auth_token(self, token: str) -> None:
        """
        Set authorization token for subsequent requests.

        Args:
            token: Access token
        """
        self.client.headers["Authorization"] = f"Bearer {token}"
        logger.debug("Authorization token set")
    
    def get_device_id(self) -> str:
        """
        Get the device ID used for API requests.
        
        Returns:
            Device ID string
        """
        return self._device_id

    def clear_auth_token(self) -> None:
        """Clear authorization token."""
        if "Authorization" in self.client.headers:
            del self.client.headers["Authorization"]
            logger.debug("Authorization token cleared")

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        await self.client.aclose()
        logger.info("IS74ApiClient closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
