"""HTTP client utilities for making requests to external APIs."""

from typing import Any, Dict, Optional
import httpx

from ..config import get_api_key


async def make_request(
    url: str, method: str = "GET", data: Dict[str, Any] | None = None
) -> Dict[str, Any] | None:
    """Make an HTTP request with optional authentication.

    Args:
        url: The URL to make the request to
        method: HTTP method (GET, POST, etc.)
        data: Optional data for the request body or query parameters

    Returns:
        JSON response as dictionary, or None/error dict if request fails
    """
    # API_KEY is optional - if not provided, requests will be made without authentication
    api_key = get_api_key()
    headers = {"Accept": "application/json"}
    if api_key:
        clean_token = api_key.strip()
        headers["Authorization"] = f"Bearer {clean_token}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            if method.upper() == "GET":
                response = await client.request(
                    method, url, headers=headers, params=data
                )
            else:
                response = await client.request(method, url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        # Return error information instead of crashing
        return {"error": f"Request failed: {str(e)}", "url": url}


async def make_request_text(
    url: str, method: str = "GET", timeout: float = 30.0
) -> Optional[str]:
    """Make an HTTP request and return text response with optional authentication.

    Args:
        url: The URL to make the request to
        method: HTTP method (GET, POST, etc.)
        timeout: Request timeout in seconds

    Returns:
        Text response as string, or None if request fails
    """
    # API_KEY is optional - if not provided, requests will be made without authentication
    api_key = get_api_key()
    headers = {}
    if api_key:
        clean_token = api_key.strip()
        headers["Authorization"] = f"Bearer {clean_token}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.request(method, url, headers=headers)
            if response.status_code == 200:
                return response.text
            return None
    except Exception:
        return None
