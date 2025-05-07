# src/fastmcp_mount/__init__.py
"""
FastMCP Mount ASGI Middleware

Provides ASGI middleware to correct endpoint path issues when mounting
FastMCP SSE applications under a sub-path in frameworks like FastAPI/Starlette.
"""

from .middleware import MountFastMCP

__version__ = "0.1.0"
__all__ = ["MountFastMCP"]
